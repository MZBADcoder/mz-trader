"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from api.deps import get_current_user, get_login_user_service, get_register_user_service
from api.schemas.auth import AuthRequest, AuthSessionResponse, CurrentUserResponse, UserResponse
from application.services import LoginUserService, RegisterUserService
from domain.entities import User


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: AuthRequest,
    service: RegisterUserService = Depends(get_register_user_service),
) -> AuthSessionResponse:
    session = await service.execute(email=payload.email, password=payload.password)
    return AuthSessionResponse(
        user=UserResponse.model_validate(session.user),
        access_token=session.access_token,
        token_type=session.token_type,
        expires_in=session.expires_in,
    )


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: AuthRequest,
    service: LoginUserService = Depends(get_login_user_service),
) -> AuthSessionResponse:
    session = await service.execute(email=payload.email, password=payload.password)
    return AuthSessionResponse(
        user=UserResponse.model_validate(session.user),
        access_token=session.access_token,
        token_type=session.token_type,
        expires_in=session.expires_in,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(user=UserResponse.model_validate(current_user))
