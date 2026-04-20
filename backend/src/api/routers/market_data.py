"""Market data routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from api.deps import (
    get_batch_snapshots_service,
    get_bars_service,
    get_current_user,
    get_market_data_capabilities_service,
)
from api.schemas.market_data import (
    BarResponse,
    BarsMetaResponse,
    BarsResponse,
    MarketDataCapabilitiesBody,
    MarketDataCapabilitiesResponse,
    SnapshotItemResponse,
    SnapshotsMetaResponse,
    SnapshotsResponse,
)
from application.services import GetBarsService, GetBatchSnapshotsService, GetMarketDataCapabilitiesService
from bootstrap.request_context import get_request_context
from domain.entities import User
from domain.exceptions import ValidationError
from domain.rules import validate_bars_query


router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/capabilities", response_model=MarketDataCapabilitiesResponse)
async def get_market_data_capabilities(
    _: User = Depends(get_current_user),
    service: GetMarketDataCapabilitiesService = Depends(get_market_data_capabilities_service),
) -> MarketDataCapabilitiesResponse:
    capabilities = await service.execute()
    return MarketDataCapabilitiesResponse(
        market_data=MarketDataCapabilitiesBody.model_validate(capabilities)
    )


@router.get("/snapshots", response_model=SnapshotsResponse)
async def get_batch_snapshots(
    tickers: str = Query(...),
    current_user: User = Depends(get_current_user),
    service: GetBatchSnapshotsService = Depends(get_batch_snapshots_service),
) -> SnapshotsResponse:
    result = await service.execute(user_id=current_user.id, tickers=tickers.split(","))
    request_id = get_request_context().request_id or ""
    return SnapshotsResponse(
        items=[SnapshotItemResponse.model_validate(item) for item in result.items],
        meta=SnapshotsMetaResponse(
            delay_minutes=result.delay_minutes,
            is_realtime=result.is_realtime,
            request_id=request_id,
        ),
    )


@router.get("/bars", response_model=BarsResponse)
async def get_bars(
    response: Response,
    ticker: str = Query(...),
    resolution: str = Query(...),
    session: str = Query(...),
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    count_back: int | None = Query(default=None),
    adjustment: str = Query(default="split_adjusted"),
    fill: str = Query(default="carry_forward"),
    include_partial: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    service: GetBarsService = Depends(get_bars_service),
) -> BarsResponse:
    query = validate_bars_query(
        ticker=ticker,
        resolution=resolution,
        session=session,
        adjustment=adjustment,
        fill=fill,
        include_partial=include_partial,
        from_time=_parse_optional_datetime(from_time),
        to_time=_parse_optional_datetime(to_time),
        count_back=count_back,
    )
    result = await service.execute(user_id=current_user.id, query=query)
    request_id = get_request_context().request_id or ""
    response.headers["X-Data-Source"] = result.meta.data_source
    response.headers["X-Partial-Range"] = str(result.meta.partial_range).lower()
    return BarsResponse(
        bars=[BarResponse.model_validate(item) for item in result.bars],
        meta=BarsMetaResponse(
            ticker=result.meta.ticker,
            resolution=result.meta.resolution,
            session=result.meta.session,
            adjustment=result.meta.adjustment,
            fill=result.meta.fill,
            requested_from=result.meta.requested_from,
            requested_to=result.meta.requested_to,
            effective_from=result.meta.effective_from,
            effective_to=result.meta.effective_to,
            effective_trading_day=result.meta.effective_trading_day.isoformat()
            if result.meta.effective_trading_day is not None
            else None,
            market_timezone=result.meta.market_timezone,
            source_granularity=result.meta.source_granularity,
            data_source=result.meta.data_source,
            partial_range=result.meta.partial_range,
            readiness=result.meta.readiness,
            calendar_shifted=result.meta.calendar_shifted,
            contains_partial_bar=result.meta.contains_partial_bar,
            delay_minutes=result.meta.delay_minutes,
            request_id=request_id,
        ),
    )


def _parse_optional_datetime(value: str | None):
    if value is None or value == "":
        return None
    from datetime import UTC, datetime

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(detail=f"datetime: Invalid RFC3339 value {value!r}.") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
