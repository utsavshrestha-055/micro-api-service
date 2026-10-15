"""Bearer session and permission dependencies."""

from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, Header, HTTPException, Request

from app.services.auth import AuthService


@dataclass(frozen=True)
class Session:
    token: str


async def require_session(
    authorization: Annotated[str | None, Header()] = None,
) -> Session:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer session required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(status_code=401, detail="Bearer session required")
    return Session(token)


async def require_permission(permission: str, request: Request, session: Session) -> None:
    service = cast(AuthService, request.app.state.auth_service)
    await service.check_permission(session.token, permission)


def permission_dependency(permission: str) -> Any:
    async def check(
        request: Request,
        session: Annotated[Session, Depends(require_session)],
    ) -> Session:
        await require_permission(permission, request, session)
        return session

    return check
