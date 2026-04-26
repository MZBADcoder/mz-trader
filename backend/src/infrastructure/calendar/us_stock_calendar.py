"""XNYS trading calendar helpers backed by exchange_calendars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import cast
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd


EASTERN_TZ = ZoneInfo("America/New_York")
PRE_MARKET_START = time(4, 0)
AFTER_HOURS_END = time(20, 0)


@dataclass(slots=True)
class SessionWindow:
    """Resolved session bounds for one trading day."""

    trading_day: date
    session: str
    start_at: datetime
    end_at: datetime


class UsStockCalendar:
    """NYSE-style trading calendar for MVP bars flows."""

    market_timezone = "America/New_York"

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar("XNYS")

    def is_trading_day(self, day: date) -> bool:
        return bool(self._calendar.is_session(self._session_label(day)))

    def previous_trading_day(self, day: date) -> date:
        session = self._calendar.date_to_session(self._session_label(day), direction="previous")
        if session.date() == day:
            session = self._calendar.previous_session(session)
        return session.date()

    def previous_or_same_trading_day(self, day: date) -> date:
        return self._calendar.date_to_session(self._session_label(day), direction="previous").date()

    def next_trading_day(self, day: date) -> date:
        session = self._calendar.date_to_session(self._session_label(day), direction="next")
        if session.date() == day:
            session = self._calendar.next_session(session)
        return session.date()

    def regular_close_time(self, day: date) -> time:
        close_at = self._calendar.session_close(self._session_label(day)).tz_convert(EASTERN_TZ)
        return close_at.timetz().replace(tzinfo=None)

    def regular_session_window(self, day: date) -> SessionWindow:
        return self.session_window(day, "regular")

    def session_window(self, day: date, session: str) -> SessionWindow:
        session_ts = self._session_label(day)
        open_at = self._to_datetime(self._calendar.session_open(session_ts))
        close_at = self._to_datetime(self._calendar.session_close(session_ts))
        if session == "pre_market":
            start = self._combine(day, PRE_MARKET_START)
            end = open_at
        elif session == "regular":
            start = open_at
            end = close_at
        elif session == "after_hours":
            start = close_at
            end = self._combine(day, AFTER_HOURS_END)
        else:
            raise ValueError(f"Unsupported session: {session}")
        return SessionWindow(trading_day=day, session=session, start_at=start, end_at=end)

    def classify_session(self, timestamp: datetime) -> tuple[date, str | None]:
        ts = self._to_timestamp(timestamp)
        local_day = ts.tz_convert(EASTERN_TZ).date()
        if not self.is_trading_day(local_day):
            return local_day, None

        pre = self.session_window(local_day, "pre_market")
        regular = self.session_window(local_day, "regular")
        after = self.session_window(local_day, "after_hours")
        dt = self._to_datetime(ts)
        if pre.start_at <= dt < pre.end_at:
            return local_day, "pre_market"
        if regular.start_at <= dt < regular.end_at:
            return local_day, "regular"
        if after.start_at <= dt < after.end_at:
            return local_day, "after_hours"
        return local_day, None

    def to_market_date(self, timestamp: datetime) -> date:
        return self._to_timestamp(timestamp).tz_convert(EASTERN_TZ).date()

    def first_trading_day_of_month(self, year: int, month: int) -> date:
        first = date(year, month, 1)
        return self._calendar.date_to_session(self._session_label(first), direction="next").date()

    def first_trading_day_of_quarter(self, year: int, quarter: int) -> date:
        month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
        return self.first_trading_day_of_month(year, month)

    def trading_days_between(self, start_day: date, end_day: date) -> list[date]:
        sessions = self._calendar.sessions_in_range(self._session_label(start_day), self._session_label(end_day))
        return [session.date() for session in sessions]

    def previous_trading_days(self, end_day: date, count: int) -> list[date]:
        end_session = self._calendar.date_to_session(self._session_label(end_day), direction="previous")
        sessions = self._calendar.sessions_window(end_session, -(count - 1))
        return [session.date() for session in sessions]

    def _combine(self, day: date, value: time) -> datetime:
        return datetime.combine(day, value, tzinfo=EASTERN_TZ).astimezone(UTC)

    def _to_timestamp(self, timestamp: datetime) -> pd.Timestamp:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return cast(pd.Timestamp, pd.Timestamp(timestamp.astimezone(UTC)))

    def _to_datetime(self, timestamp: pd.Timestamp) -> datetime:
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(UTC)
        return timestamp.to_pydatetime().astimezone(UTC)

    def _session_label(self, day: date) -> pd.Timestamp:
        return cast(pd.Timestamp, pd.Timestamp(day))
