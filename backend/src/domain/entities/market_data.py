"""Market data domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class MarketDataMode:
    """Resolved runtime mode for market data behavior."""

    delay_minutes: int
    supports_stream: bool = False

    @property
    def is_realtime(self) -> bool:
        return self.delay_minutes == 0


@dataclass(slots=True)
class MarketDataCapabilities:
    """Frontend-facing market data capability envelope."""

    delay_minutes: int
    is_realtime: bool
    supports_stream: bool


@dataclass(slots=True)
class Snapshot:
    """Unified snapshot view returned by the backend."""

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
    fetched_at: datetime
    data_source: str


@dataclass(slots=True)
class BatchSnapshotsResult:
    """Application result for a batch snapshot request."""

    items: list[Snapshot]
    delay_minutes: int
    is_realtime: bool


@dataclass(slots=True)
class SnapshotCoordinatorRefreshResult:
    """Summary of one coordinator refresh run."""

    status: str
    total_tickers: int
    refreshed_tickers: int
    failed_tickers: list[str]
    skip_reason: str | None = None
