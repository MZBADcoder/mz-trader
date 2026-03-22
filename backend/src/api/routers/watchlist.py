"""Watchlist routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.deps import (
    get_add_watchlist_item_service,
    get_current_user,
    get_delete_watchlist_item_service,
    get_watchlist_service,
)
from api.schemas.watchlist import (
    CreateWatchlistItemRequest,
    CreateWatchlistItemResponse,
    WatchlistItemResponse,
    WatchlistResponse,
)
from application.services import AddWatchlistItemService, DeleteWatchlistItemService, GetWatchlistService
from domain.entities import User


router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistResponse)
async def list_watchlist(
    current_user: User = Depends(get_current_user),
    service: GetWatchlistService = Depends(get_watchlist_service),
) -> WatchlistResponse:
    items = await service.execute(user_id=current_user.id)
    return WatchlistResponse(items=[WatchlistItemResponse.model_validate(item) for item in items])


@router.post("/items", response_model=CreateWatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(
    payload: CreateWatchlistItemRequest,
    current_user: User = Depends(get_current_user),
    service: AddWatchlistItemService = Depends(get_add_watchlist_item_service),
) -> CreateWatchlistItemResponse:
    item = await service.execute(user_id=current_user.id, ticker=payload.ticker)
    return CreateWatchlistItemResponse(item=WatchlistItemResponse.model_validate(item))


@router.delete("/items/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(
    ticker: str,
    current_user: User = Depends(get_current_user),
    service: DeleteWatchlistItemService = Depends(get_delete_watchlist_item_service),
) -> Response:
    await service.execute(user_id=current_user.id, ticker=ticker)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
