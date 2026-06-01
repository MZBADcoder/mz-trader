"""Get bars use case."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import ceil
from typing import Callable

from bootstrap.request_context import bind_request_context
from domain.entities import Bar, BarsMeta, BarsQuery, BarsResult, CanonicalBar, TickerBarsState
from domain.exceptions import MarketBarsRangeTooLargeError
from domain.rules import MARKET_BARS_1D_RETENTION_YEARS, MARKET_BARS_MAX_ESTIMATED_OUTPUT_ROWS
from infrastructure.calendar import SessionWindow, UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory


INTRADAY_RESOLUTION_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
}
HIGHER_DEFAULT_COUNT_BACK = {"1D": 120, "1W": 104, "1M": 120, "1Q": 80}
HigherBucketKey = tuple[int, int] | tuple[int, int, int]
class GetBarsService:
    """Resolve unified chart bars from canonical DB storage only."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        calendar: UsStockCalendar,
        mode,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._calendar = calendar
        self._mode = mode
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self, *, user_id: str, query: BarsQuery) -> BarsResult:
        bind_request_context(user_id=user_id, ticker=query.ticker)
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)

        if query.resolution in INTRADAY_RESOLUTION_MINUTES or query.session != "regular":
            return await self._execute_intraday_source(query=query, effective_now=effective_now)
        return await self._execute_daily_source(query=query, effective_now=effective_now)

    async def _execute_intraday_source(self, *, query: BarsQuery, effective_now: datetime) -> BarsResult:
        anchor = min(query.to_time or effective_now, effective_now)
        windows, calendar_shifted = self._resolve_intraday_windows(query=query, anchor=anchor)
        self._ensure_estimated_rows(
            query=query,
            windows=windows,
            effective_now=effective_now,
        )

        async with self._uow_factory.build() as uow:
            state = await uow.ticker_bars_state.get(ticker=query.ticker)
            db_rows: list[CanonicalBar] = []
            for window in windows:
                start_at, end_at = self._resolve_intraday_window_bounds(
                    query=query,
                    window=window,
                    effective_now=effective_now,
                )
                if start_at >= end_at:
                    continue
                db_rows.extend(
                    await uow.bars.list_1m(
                        ticker=query.ticker,
                        adjustment=query.adjustment,
                        start_at=start_at,
                        end_at=end_at,
                        session_kind=query.session,
                    )
                )
            bars = await self._build_intraday_bars(
                uow=uow,
                query=query,
                windows=windows,
                source_rows=db_rows,
                effective_now=effective_now,
            )

        bars = self._filter_explicit_range_bars(query=query, bars=bars)
        if query.from_time is None:
            bars = self._apply_latest_tail_slice(query=query, bars=bars)

        readiness = self._resolve_readiness(state=state, has_any_rows=bool(db_rows or bars))
        partial_range = self._resolve_intraday_partial_range(
            query=query,
            state=state,
            readiness=readiness,
        )
        effective_from = bars[0].time if bars else (windows[0].start_at if windows else None)
        effective_trading_day = windows[-1].trading_day if windows else None
        return BarsResult(
            bars=bars,
            meta=BarsMeta(
                ticker=query.ticker,
                resolution=query.resolution,
                session=query.session,
                adjustment=query.adjustment,
                fill=query.fill,
                requested_from=query.from_time,
                requested_to=query.to_time,
                effective_from=effective_from,
                effective_to=anchor if query.from_time is None else query.to_time,
                effective_trading_day=effective_trading_day,
                market_timezone=self._calendar.market_timezone,
                source_granularity="1m",
                data_source="db",
                partial_range=partial_range,
                readiness=readiness,
                calendar_shifted=calendar_shifted,
                contains_partial_bar=any(not bar.is_final for bar in bars),
                delay_minutes=self._mode.delay_minutes,
            ),
        )

    async def _execute_daily_source(self, *, query: BarsQuery, effective_now: datetime) -> BarsResult:
        anchor = min(query.to_time or effective_now, effective_now)
        anchor_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(anchor))
        count_back = query.count_back or HIGHER_DEFAULT_COUNT_BACK[query.resolution]
        if query.from_time is not None:
            start_day, end_day = self._resolve_explicit_daily_range(query=query)
        else:
            start_day, end_day = self._resolve_latest_daily_range(
                anchor_day=anchor_day,
                resolution=query.resolution,
                count_back=count_back,
            )

        async with self._uow_factory.build() as uow:
            state = await uow.ticker_bars_state.get(ticker=query.ticker)
            completed_end_day = end_day
            current_partial = self._build_current_regular_day_window(
                anchor=anchor,
                effective_now=effective_now,
                query=query,
            )
            if current_partial is not None and current_partial.trading_day <= completed_end_day:
                completed_end_day = self._calendar.previous_trading_day(current_partial.trading_day)

            db_days: list[CanonicalBar] = []
            if start_day <= completed_end_day:
                db_days = await uow.bars.list_1d(
                    ticker=query.ticker,
                    adjustment=query.adjustment,
                    start_day=start_day,
                    end_day=completed_end_day,
                )

            current_day_bar: CanonicalBar | None = None
            if current_partial is not None:
                current_day_bar = await self._build_current_regular_day_bar(
                    uow=uow,
                    query=query,
                    window=current_partial,
                    effective_now=effective_now,
                )

        contributions = list(db_days)
        if current_day_bar is not None:
            contributions.append(current_day_bar)
        bars = self._build_higher_bars(query=query, contributions=contributions)
        bars = self._filter_explicit_range_bars(query=query, bars=bars)
        if query.from_time is None:
            bars = self._apply_latest_tail_slice(query=query, bars=bars)

        readiness = self._resolve_readiness(state=state, has_any_rows=bool(contributions))
        partial_range = self._resolve_daily_partial_range(query=query, state=state, readiness=readiness)
        return BarsResult(
            bars=bars,
            meta=BarsMeta(
                ticker=query.ticker,
                resolution=query.resolution,
                session=query.session,
                adjustment=query.adjustment,
                fill=query.fill,
                requested_from=query.from_time,
                requested_to=query.to_time,
                effective_from=bars[0].time if bars else None,
                effective_to=anchor,
                effective_trading_day=contributions[-1].trading_day if contributions else None,
                market_timezone=self._calendar.market_timezone,
                source_granularity="1d",
                data_source="db",
                partial_range=partial_range,
                readiness=readiness,
                calendar_shifted=False,
                contains_partial_bar=any(not bar.is_final for bar in bars),
                delay_minutes=self._mode.delay_minutes,
            ),
        )

    def _resolve_intraday_windows(self, *, query: BarsQuery, anchor: datetime) -> tuple[list[SessionWindow], bool]:
        if query.from_time is not None:
            return self._explicit_intraday_windows(query=query), False

        local_day = self._calendar.to_market_date(anchor)
        if not self._calendar.is_trading_day(local_day):
            trading_day = self._calendar.previous_trading_day(local_day)
            return [self._calendar.session_window(trading_day, query.session)], True

        window = self._calendar.session_window(local_day, query.session)
        if anchor <= window.start_at:
            return [], False
        return [window], False

    def _explicit_intraday_windows(self, *, query: BarsQuery) -> list[SessionWindow]:
        assert query.from_time is not None
        assert query.to_time is not None
        start_local = self._calendar.to_market_date(query.from_time)
        end_local = self._calendar.to_market_date(query.to_time)
        windows: list[SessionWindow] = []
        for trading_day in self._calendar.trading_days_between(start_local, end_local):
            session_window = self._calendar.session_window(trading_day, query.session)
            if session_window.end_at <= query.from_time or session_window.start_at >= query.to_time:
                continue
            windows.append(session_window)
        return windows

    async def _build_intraday_bars(
        self,
        *,
        uow,
        query: BarsQuery,
        windows: list[SessionWindow],
        source_rows: list[CanonicalBar],
        effective_now: datetime,
    ) -> list[Bar]:
        rows_by_start = {row.bucket_start_at: row for row in source_rows}
        output: list[Bar] = []

        for window in windows:
            lower_bound, upper_bound = self._resolve_intraday_window_bounds(
                query=query,
                window=window,
                effective_now=effective_now,
            )
            if lower_bound >= upper_bound:
                continue
            expected_starts = self._expected_bucket_starts(
                resolution=query.resolution,
                window=window,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                include_partial=query.include_partial,
            )
            seed_close = await self._resolve_fill_seed(
                uow=uow,
                ticker=query.ticker,
                adjustment=query.adjustment,
                session=query.session,
                trading_day=window.trading_day,
            )
            if query.resolution == "1m":
                for bucket_start in expected_starts:
                    child = rows_by_start.get(bucket_start)
                    bucket_end = min(bucket_start + timedelta(minutes=1), window.end_at)
                    if child is None:
                        if query.fill == "carry_forward" and seed_close is not None:
                            output.append(
                                self._make_synthetic_bar(
                                    time=bucket_start,
                                    close=seed_close,
                                    bucket_end=bucket_end,
                                    effective_now=effective_now,
                                )
                            )
                        continue
                    output.append(self._to_response_bar(child))
                    seed_close = child.close
                continue

            grouped: dict[datetime, list[CanonicalBar]] = defaultdict(list)
            resolution_minutes = 1 if query.resolution == "1D" else INTRADAY_RESOLUTION_MINUTES[query.resolution]
            for row in source_rows:
                if row.bucket_start_at < window.start_at or row.bucket_start_at >= window.end_at:
                    continue
                parent_start = (
                    window.start_at
                    if query.resolution == "1D"
                    else self._bucket_start_for_intraday(
                        child_start=row.bucket_start_at,
                        session_start=window.start_at,
                        resolution_minutes=resolution_minutes,
                    )
                )
                grouped[parent_start].append(row)

            for bucket_start in expected_starts:
                bucket_end = self._bucket_end_for_intraday(
                    bucket_start=bucket_start,
                    window=window,
                    resolution=query.resolution,
                )
                children = grouped.get(bucket_start, [])
                if not children:
                    if query.fill == "carry_forward" and seed_close is not None:
                        output.append(
                            self._make_synthetic_bar(
                                time=bucket_start,
                                close=seed_close,
                                bucket_end=bucket_end,
                                effective_now=effective_now,
                            )
                        )
                    continue
                bar = self._aggregate_bucket(children=children, time=bucket_start, bucket_end=bucket_end, effective_now=effective_now)
                output.append(bar)
                seed_close = bar.close
        return output

    async def _build_current_regular_day_bar(
        self,
        *,
        uow,
        query: BarsQuery,
        window: SessionWindow,
        effective_now: datetime,
    ) -> CanonicalBar | None:
        rows = await uow.bars.list_1m(
            ticker=query.ticker,
            adjustment=query.adjustment,
            start_at=window.start_at,
            end_at=min(window.end_at, effective_now),
            session_kind="regular",
        )
        if not rows:
            return None
        return self._aggregate_canonical_rows(
            rows=rows,
            ticker=query.ticker,
            adjustment=query.adjustment,
            granularity="1d",
            session_kind="regular",
            trading_day=window.trading_day,
            bucket_start_at=window.start_at,
            bucket_end=window.end_at,
            effective_now=effective_now,
        )

    def _build_current_regular_day_window(
        self,
        *,
        anchor: datetime,
        effective_now: datetime,
        query: BarsQuery,
    ) -> SessionWindow | None:
        effective_day = self._current_trading_day(effective_now=effective_now)
        if effective_day is None:
            return None
        anchor_day = self._calendar.to_market_date(anchor)
        if anchor_day != effective_day:
            return None
        regular_window = self._calendar.regular_session_window(anchor_day)
        if anchor <= regular_window.start_at:
            return None
        if not query.include_partial and anchor < regular_window.end_at:
            return None
        return regular_window

    def _build_higher_bars(self, *, query: BarsQuery, contributions: list[CanonicalBar]) -> list[Bar]:
        if not contributions:
            return []
        if query.resolution == "1D":
            return [self._to_response_bar(item) for item in contributions]

        grouped: dict[HigherBucketKey, list[CanonicalBar]] = defaultdict(list)
        for item in contributions:
            grouped[self._higher_bucket_key(resolution=query.resolution, trading_day=item.trading_day)].append(item)

        bars: list[Bar] = []
        for _, children in sorted(grouped.items(), key=lambda item: item[1][0].bucket_start_at):
            ordered_children = sorted(children, key=lambda child: child.bucket_start_at)
            bars.append(
                Bar(
                    time=ordered_children[0].bucket_start_at,
                    open=ordered_children[0].open,
                    high=max(child.high for child in ordered_children),
                    low=min(child.low for child in ordered_children),
                    close=ordered_children[-1].close,
                    volume=sum(child.volume for child in ordered_children),
                    vw=self._weighted_average(ordered_children),
                    trade_count=sum(child.trade_count for child in ordered_children),
                    is_final=all(child.is_final for child in ordered_children),
                    is_synthetic=False,
                )
            )
        return bars

    def _expected_bucket_starts(
        self,
        *,
        resolution: str,
        window: SessionWindow,
        lower_bound: datetime,
        upper_bound: datetime,
        include_partial: bool,
    ) -> list[datetime]:
        if resolution == "1D":
            if upper_bound <= window.start_at:
                return []
            if window.start_at < lower_bound:
                return []
            if not include_partial and upper_bound < window.end_at:
                return []
            return [window.start_at]

        minutes = INTRADAY_RESOLUTION_MINUTES[resolution]
        capped_upper_bound = min(window.end_at, upper_bound)
        if capped_upper_bound <= window.start_at:
            return []
        starts: list[datetime] = []
        current = window.start_at
        while current < capped_upper_bound:
            bucket_end = min(current + timedelta(minutes=minutes), window.end_at)
            if current >= lower_bound and (include_partial or bucket_end <= capped_upper_bound):
                starts.append(current)
            current += timedelta(minutes=minutes)
        return starts

    def _bucket_start_for_intraday(self, *, child_start: datetime, session_start: datetime, resolution_minutes: int) -> datetime:
        delta_minutes = int((child_start - session_start).total_seconds() // 60)
        bucket_offset = (delta_minutes // resolution_minutes) * resolution_minutes
        return session_start + timedelta(minutes=bucket_offset)

    def _bucket_end_for_intraday(self, *, bucket_start: datetime, window: SessionWindow, resolution: str) -> datetime:
        if resolution == "1D":
            return window.end_at
        return min(bucket_start + timedelta(minutes=INTRADAY_RESOLUTION_MINUTES[resolution]), window.end_at)

    async def _resolve_fill_seed(self, *, uow, ticker: str, adjustment: str, session: str, trading_day: date) -> float | None:
        if session in {"pre_market", "regular"}:
            previous_day = self._calendar.previous_trading_day(trading_day)
            previous_rows = await uow.bars.list_1d(
                ticker=ticker,
                adjustment=adjustment,
                start_day=previous_day,
                end_day=previous_day,
            )
            return previous_rows[-1].close if previous_rows else None

        regular_window = self._calendar.regular_session_window(trading_day)
        regular_rows = await uow.bars.list_1m(
            ticker=ticker,
            adjustment=adjustment,
            start_at=regular_window.start_at,
            end_at=regular_window.end_at,
            session_kind="regular",
        )
        if regular_rows:
            return regular_rows[-1].close
        previous_day = self._calendar.previous_trading_day(trading_day)
        previous_rows = await uow.bars.list_1d(
            ticker=ticker,
            adjustment=adjustment,
            start_day=previous_day,
            end_day=previous_day,
        )
        return previous_rows[-1].close if previous_rows else None

    def _aggregate_bucket(
        self,
        *,
        children: list[CanonicalBar],
        time: datetime,
        bucket_end: datetime,
        effective_now: datetime,
    ) -> Bar:
        return Bar(
            time=time,
            open=children[0].open,
            high=max(child.high for child in children),
            low=min(child.low for child in children),
            close=children[-1].close,
            volume=sum(child.volume for child in children),
            vw=self._weighted_average(children),
            trade_count=sum(child.trade_count for child in children),
            is_final=bucket_end <= effective_now and all(child.is_final for child in children),
            is_synthetic=False,
        )

    def _aggregate_canonical_rows(
        self,
        *,
        rows: list[CanonicalBar],
        ticker: str,
        adjustment: str,
        granularity: str,
        session_kind: str,
        trading_day: date,
        bucket_start_at: datetime,
        bucket_end: datetime,
        effective_now: datetime,
    ) -> CanonicalBar:
        now_synced_at = self._now_provider().astimezone(UTC)
        return CanonicalBar(
            ticker=ticker,
            adjustment=adjustment,
            granularity=granularity,
            bucket_start_at=bucket_start_at,
            trading_day=trading_day,
            session_kind=session_kind,
            open=rows[0].open,
            high=max(row.high for row in rows),
            low=min(row.low for row in rows),
            close=rows[-1].close,
            volume=sum(row.volume for row in rows),
            vw=self._weighted_average(rows),
            trade_count=sum(row.trade_count for row in rows),
            provider_updated_at=max(row.provider_updated_at for row in rows),
            is_final=bucket_end <= effective_now and all(row.is_final for row in rows),
            first_synced_at=now_synced_at,
            last_synced_at=now_synced_at,
        )

    def _to_response_bar(self, row: CanonicalBar) -> Bar:
        return Bar(
            time=row.bucket_start_at,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            vw=row.vw,
            trade_count=row.trade_count,
            is_final=row.is_final,
            is_synthetic=False,
        )

    def _make_synthetic_bar(self, *, time: datetime, close: float, bucket_end: datetime, effective_now: datetime) -> Bar:
        return Bar(
            time=time,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0,
            vw=None,
            trade_count=0,
            is_final=bucket_end <= effective_now,
            is_synthetic=True,
        )

    def _weighted_average(self, rows: list[CanonicalBar]) -> float | None:
        weighted_total = 0.0
        total_volume = 0
        for row in rows:
            if row.vw is None or row.volume <= 0:
                continue
            weighted_total += row.vw * row.volume
            total_volume += row.volume
        if total_volume <= 0:
            return None
        return weighted_total / total_volume

    def _apply_latest_tail_slice(self, *, query: BarsQuery, bars: list[Bar]) -> list[Bar]:
        count_back = query.count_back
        if count_back is None:
            count_back = HIGHER_DEFAULT_COUNT_BACK.get(query.resolution)
        if count_back is None:
            return bars
        return bars[-count_back:]

    def _ensure_estimated_rows(
        self,
        *,
        query: BarsQuery,
        windows: list[SessionWindow],
        effective_now: datetime,
    ) -> None:
        estimated = 0
        for window in windows:
            lower_bound, upper_bound = self._resolve_intraday_window_bounds(
                query=query,
                window=window,
                effective_now=effective_now,
            )
            if lower_bound >= upper_bound:
                continue
            estimated += len(
                self._expected_bucket_starts(
                    resolution=query.resolution,
                    window=window,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    include_partial=query.include_partial,
                )
            )
        if estimated > MARKET_BARS_MAX_ESTIMATED_OUTPUT_ROWS:
            raise MarketBarsRangeTooLargeError()

    def _resolve_readiness(self, *, state: TickerBarsState | None, has_any_rows: bool) -> str:
        if state is not None:
            return state.status
        return "ready" if has_any_rows else "pending"

    def _resolve_intraday_partial_range(self, *, query: BarsQuery, state: TickerBarsState | None, readiness: str) -> bool:
        if readiness != "ready":
            return True
        if state is None or query.from_time is None or state.earliest_1m_trading_day is None:
            return False
        return self._calendar.to_market_date(query.from_time) < state.earliest_1m_trading_day

    def _resolve_daily_partial_range(self, *, query: BarsQuery, state: TickerBarsState | None, readiness: str) -> bool:
        if readiness != "ready":
            return True
        if state is None or query.from_time is None or state.earliest_1d_trading_day is None:
            return False
        return self._calendar.to_market_date(query.from_time) < state.earliest_1d_trading_day

    def _resolve_intraday_window_bounds(
        self,
        *,
        query: BarsQuery,
        window: SessionWindow,
        effective_now: datetime,
    ) -> tuple[datetime, datetime]:
        lower_bound = window.start_at
        upper_bound = window.end_at
        if query.from_time is not None and query.to_time is not None:
            lower_bound = max(lower_bound, query.from_time)
            upper_bound = min(upper_bound, query.to_time)
        if window.trading_day == self._calendar.to_market_date(effective_now):
            upper_bound = min(upper_bound, effective_now)
        return lower_bound, upper_bound

    def _filter_explicit_range_bars(self, *, query: BarsQuery, bars: list[Bar]) -> list[Bar]:
        if query.from_time is None or query.to_time is None:
            return bars
        return [bar for bar in bars if query.from_time <= bar.time < query.to_time]

    def _resolve_explicit_daily_range(self, *, query: BarsQuery) -> tuple[date, date]:
        assert query.from_time is not None
        assert query.to_time is not None
        start_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(query.from_time))
        end_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(query.to_time))
        if query.resolution == "1D":
            return start_day, end_day
        return (
            self._higher_bucket_start_day(resolution=query.resolution, trading_day=start_day),
            self._higher_bucket_end_day(resolution=query.resolution, trading_day=end_day),
        )

    def _resolve_latest_daily_range(
        self,
        *,
        anchor_day: date,
        resolution: str,
        count_back: int,
    ) -> tuple[date, date]:
        if resolution == "1D":
            return self._calendar.previous_trading_days(anchor_day, max(count_back, 1))[0], anchor_day

        earliest_bucket_start_day = self._higher_bucket_start_day(
            resolution=resolution,
            trading_day=self._daily_source_floor_day(anchor_day=anchor_day),
        )
        bucket_day = anchor_day
        for _ in range(max(count_back, 1)):
            bucket_start_day = self._higher_bucket_start_day(resolution=resolution, trading_day=bucket_day)
            if bucket_start_day <= earliest_bucket_start_day:
                return earliest_bucket_start_day, anchor_day
            bucket_day = self._calendar.previous_trading_day(bucket_start_day)
        resolved_start_day = self._higher_bucket_start_day(resolution=resolution, trading_day=bucket_day)
        return max(resolved_start_day, earliest_bucket_start_day), anchor_day

    def _daily_source_floor_day(self, *, anchor_day: date) -> date:
        return self._calendar.previous_or_same_trading_day(
            self._subtract_years(anchor_day, MARKET_BARS_1D_RETENTION_YEARS)
        )

    def _higher_bucket_key(self, *, resolution: str, trading_day: date) -> HigherBucketKey:
        if resolution == "1W":
            week_start = trading_day - timedelta(days=trading_day.weekday())
            return (week_start.year, week_start.month, week_start.day)
        if resolution == "1M":
            return (trading_day.year, trading_day.month)
        quarter = ceil(trading_day.month / 3)
        return (trading_day.year, quarter)

    def _higher_bucket_start_day(self, *, resolution: str, trading_day: date) -> date:
        if resolution == "1W":
            calendar_week_start = trading_day - timedelta(days=trading_day.weekday())
            return self._calendar.next_trading_day(calendar_week_start - timedelta(days=1))
        if resolution == "1M":
            return self._calendar.first_trading_day_of_month(trading_day.year, trading_day.month)
        quarter = ceil(trading_day.month / 3)
        return self._calendar.first_trading_day_of_quarter(trading_day.year, quarter)

    def _higher_bucket_end_day(self, *, resolution: str, trading_day: date) -> date:
        if resolution == "1W":
            next_period_start = trading_day - timedelta(days=trading_day.weekday()) + timedelta(days=7)
        elif resolution == "1M":
            if trading_day.month == 12:
                next_period_start = date(trading_day.year + 1, 1, 1)
            else:
                next_period_start = date(trading_day.year, trading_day.month + 1, 1)
        else:
            quarter = ceil(trading_day.month / 3)
            if quarter == 4:
                next_period_start = date(trading_day.year + 1, 1, 1)
            else:
                next_period_start = date(trading_day.year, quarter * 3 + 1, 1)
        return self._calendar.previous_trading_day(next_period_start)

    def _current_trading_day(self, *, effective_now: datetime) -> date | None:
        market_day = self._calendar.to_market_date(effective_now)
        if not self._calendar.is_trading_day(market_day):
            return None
        return market_day

    def _subtract_years(self, value: date, years: int) -> date:
        try:
            return value.replace(year=value.year - years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year - years)
