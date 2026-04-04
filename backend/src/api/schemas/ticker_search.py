"""Ticker search DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TickerSearchItemResponse(BaseModel):
    """Ticker search result returned to the client."""

    ticker: str
    name: str
    primary_exchange: str
    type: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


class TickerSearchResponse(BaseModel):
    """Response envelope for ticker search."""

    items: list[TickerSearchItemResponse]

    model_config = ConfigDict(from_attributes=True)
