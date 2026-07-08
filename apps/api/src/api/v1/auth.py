"""Rotas de autenticação: register, login, refresh, /me.

Login e refresh são custom porque emitimos par access+refresh (fastapi-users
nativo entrega só o access). O register e o /me reaproveitam o fastapi-users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ...core.security import get_jwt_strategy, get_refresh_strategy
from ...core.users import UserManager, current_active_user, fastapi_users, get_user_manager
from ...models.usuario import Usuario
from ...schemas.user import UserCreate, UserRead

router = APIRouter(tags=["auth"])

# POST /auth/register
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/auth/login", response_model=TokenPair)
async def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
) -> TokenPair:
    user = await user_manager.authenticate(credentials)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS",
        )
    access = await get_jwt_strategy().write_token(user)
    refresh = await get_refresh_strategy().write_token(user)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    user_manager: UserManager = Depends(get_user_manager),
) -> TokenPair:
    user = await get_refresh_strategy().read_token(body.refresh_token, user_manager)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_REFRESH_TOKEN",
        )
    access = await get_jwt_strategy().write_token(user)
    new_refresh = await get_refresh_strategy().write_token(user)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserRead, tags=["me"])
async def me(user: Usuario = Depends(current_active_user)) -> Usuario:
    return user
