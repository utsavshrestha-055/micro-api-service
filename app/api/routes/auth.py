"""Public authentication routes and session-bound identity."""

from typing import cast

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import Session, require_session
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, object]:
    return await cast(AuthService, request.app.state.auth_service).login(payload)


@router.post("/register")
async def register(payload: RegisterRequest, request: Request) -> dict[str, object]:
    return await cast(AuthService, request.app.state.auth_service).register(payload)


@router.post("/logout")
async def logout(
    request: Request, session: Session = Depends(require_session)
) -> dict[str, object]:
    return await cast(AuthService, request.app.state.auth_service).logout(session.token)


@router.get("/me")
async def current_user(
    request: Request, session: Session = Depends(require_session)
) -> dict[str, object]:
    return await cast(AuthService, request.app.state.auth_service).current_user(session.token)
