"""Reference ticker search routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, get_search_reference_tickers_service
from api.schemas.reference import TickerSearchItemResponse, TickerSearchResponse
from application.services import SearchReferenceTickersService
from domain.entities import User


router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/tickers/search", response_model=TickerSearchResponse)
async def search_reference_tickers(
    *,
    query: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    _: User = Depends(get_current_user),
    service: SearchReferenceTickersService = Depends(get_search_reference_tickers_service),
) -> TickerSearchResponse:
    items = await service.execute(query=query, limit=limit)
    return TickerSearchResponse(items=[TickerSearchItemResponse.model_validate(item) for item in items])
