"""Market data routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import (
    get_batch_snapshots_service,
    get_current_user,
    get_market_data_capabilities_service,
)
from api.schemas.market_data import (
    MarketDataCapabilitiesBody,
    MarketDataCapabilitiesResponse,
    SnapshotItemResponse,
    SnapshotsMetaResponse,
    SnapshotsResponse,
)
from application.services import GetBatchSnapshotsService, GetMarketDataCapabilitiesService
from bootstrap.request_context import get_request_context
from domain.entities import User


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
