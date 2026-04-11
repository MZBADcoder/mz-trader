"""Market data DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MarketDataCapabilitiesBody(BaseModel):
    """Frontend-facing market data capability body."""

    delay_minutes: int
    is_realtime: bool
    supports_stream: bool

    model_config = ConfigDict(from_attributes=True)


class MarketDataCapabilitiesResponse(BaseModel):
    """Response envelope for market data capabilities."""

    market_data: MarketDataCapabilitiesBody


class SnapshotItemResponse(BaseModel):
    """Normalized snapshot item."""

    ticker: str
    last: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: int
    prev_close: float
    market_status: str
    delay_minutes: int
    is_realtime: bool
    provider_updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SnapshotsMetaResponse(BaseModel):
    """Metadata for a snapshot batch response."""

    delay_minutes: int
    is_realtime: bool
    request_id: str


class SnapshotsResponse(BaseModel):
    """Response envelope for batch snapshots."""

    items: list[SnapshotItemResponse]
    meta: SnapshotsMetaResponse
