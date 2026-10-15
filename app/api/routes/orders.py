"""HTTP validation and endpoints for customer-scoped orders."""

from typing import cast

from fastapi import APIRouter, Depends, Header, Path, Query, Request

from app.api.dependencies import Session, permission_dependency
from app.schemas.orders import CreateOrderRequest
from app.services.orders import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("")
async def create_order(
    payload: CreateOrderRequest,
    request: Request,
    idempotency_key: str = Header(min_length=1, max_length=128, pattern="^[A-Za-z0-9._:-]+$"),
    session: Session = Depends(permission_dependency("orders.create")),
) -> dict[str, object]:
    return await cast(OrderService, request.app.state.order_service).create_order(
        payload, session.token, idempotency_key
    )


@router.get("")
async def list_orders(
    request: Request,
    page_size: int = Query(default=20, ge=1, le=100),
    page_token: str = Query(default="", max_length=2048),
    session: Session = Depends(permission_dependency("orders.read")),
) -> dict[str, object]:
    return await cast(OrderService, request.app.state.order_service).list_orders(
        session.token, page_size, page_token
    )


@router.get("/{order_id}")
async def get_order(
    request: Request,
    order_id: str = Path(..., min_length=1, max_length=128),
    session: Session = Depends(permission_dependency("orders.read")),
) -> dict[str, object]:
    return await cast(OrderService, request.app.state.order_service).get_order(
        session.token, order_id
    )


@router.post("/{order_id}/cancel")
async def cancel_order(
    request: Request,
    order_id: str = Path(..., min_length=1, max_length=128),
    note: str = Query(default="", max_length=500),
    session: Session = Depends(permission_dependency("orders.cancel")),
) -> dict[str, object]:
    return await cast(OrderService, request.app.state.order_service).cancel_order(
        session.token, order_id, note
    )
