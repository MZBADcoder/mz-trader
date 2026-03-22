"""Ticker reference domain entities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TickerSearchResult:
    """Normalized ticker reference item returned to the application."""

    ticker: str
    name: str
    primary_exchange: str
    type: str
    active: bool
