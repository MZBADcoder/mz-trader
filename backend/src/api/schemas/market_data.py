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


class BarResponse(BaseModel):
    """Frontend-facing chart bar."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vw: float | None
    trade_count: int
    is_final: bool
    is_synthetic: bool

    model_config = ConfigDict(from_attributes=True)


class BarsMetaResponse(BaseModel):
    """Metadata returned with a bars response."""

    ticker: str
    resolution: str
    session: str
    adjustment: str
    fill: str
    requested_from: datetime | None
    requested_to: datetime | None
    effective_from: datetime | None
    effective_to: datetime | None
    effective_trading_day: str | None
    market_timezone: str
    source_granularity: str
    data_source: str
    partial_range: bool
    readiness: str
    calendar_shifted: bool
    contains_partial_bar: bool
    delay_minutes: int
    request_id: str


class BarsResponse(BaseModel):
    """Response envelope for chart bars."""

    bars: list[BarResponse]
    meta: BarsMetaResponse
