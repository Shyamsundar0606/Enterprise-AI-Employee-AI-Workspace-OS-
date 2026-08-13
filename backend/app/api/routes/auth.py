from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.database.session import get_db_session
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    TokenPair,
    TokenRefreshRequest,
    UserCreate,
    UserOut,
)
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    rotate_refresh_token,
    store_refresh_token,
    user_to_out,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
async def register(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    user = await create_user(session, payload)
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    await store_refresh_token(session, user, refresh_token)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_to_out(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    user = await authenticate_user(session, payload.email.lower(), payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    await store_refresh_token(session, user, refresh_token)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_to_out(user),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: TokenRefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPair:
    access_token, refresh_token = await rotate_refresh_token(session, payload.refresh_token)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)) -> UserOut:
    return user_to_out(current_user)


@router.get("/admin")
async def admin_only(current_user: User = Depends(require_admin)) -> dict[str, str]:
    return {"message": f"Hello {current_user.username}"}
