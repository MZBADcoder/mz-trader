"""Market data domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


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


@dataclass(slots=True)
class ProviderBar:
    """One provider-sourced aggregate bar before canonical enrichment."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vw: float | None
    trade_count: int
    provider_updated_at: datetime


@dataclass(slots=True)
class CanonicalBar:
    """Persisted canonical bar row."""

    ticker: str
    adjustment: str
    granularity: str
    bucket_start_at: datetime
    trading_day: date
    session_kind: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vw: float | None
    trade_count: int
    provider_updated_at: datetime
    is_final: bool
    first_synced_at: datetime
    last_synced_at: datetime


@dataclass(slots=True)
class Bar:
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


@dataclass(slots=True)
class BarsMeta:
    """Metadata returned alongside a bars response."""

    ticker: str
    resolution: str
    session: str
    adjustment: str
    fill: str
    requested_from: datetime | None
    requested_to: datetime | None
    effective_from: datetime | None
    effective_to: datetime | None
    effective_trading_day: date | None
    market_timezone: str
    source_granularity: str
    data_source: str
    partial_range: bool
    readiness: str
    calendar_shifted: bool
    contains_partial_bar: bool
    delay_minutes: int


@dataclass(slots=True)
class BarsResult:
    """Application result for the unified bars endpoint."""

    bars: list[Bar]
    meta: BarsMeta


@dataclass(slots=True)
class BarsQuery:
    """Validated bars query passed into the application layer."""

    ticker: str
    resolution: str
    session: str
    adjustment: str
    fill: str
    include_partial: bool
    from_time: datetime | None
    to_time: datetime | None
    count_back: int | None


@dataclass(slots=True)
class TickerBarsState:
    """Ticker-level readiness and maintenance status for bars."""

    ticker: str
    status: str
    bootstrap_requested_at: datetime | None
    bootstrap_started_at: datetime | None
    bootstrap_finished_at: datetime | None
    bootstrap_failed_at: datetime | None
    last_reconciled_at: datetime | None
    earliest_1m_trading_day: date | None
    last_1m_trading_day: date | None
    last_1m_bucket_start_at: datetime | None
    earliest_1d_trading_day: date | None
    latest_1d_trading_day: date | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class BarsMaintenanceResult:
    """Summary of one bars maintenance run."""

    status: str
    total_tickers: int = 0
    processed_tickers: int = 0
    failed_tickers: list[str] | None = None
    skip_reason: str | None = None
    deleted_1m_rows: int = 0
    deleted_1d_rows: int = 0
