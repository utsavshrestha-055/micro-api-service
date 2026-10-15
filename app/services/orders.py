"""Customer-scoped order protobuf construction, calls and JSON mapping."""

import json

import grpc
from fastapi import HTTPException
from google.protobuf.json_format import MessageToDict

from app.api.errors import grpc_http_error
from app.clients.order_client import OrderClient
from app.schemas.orders import CreateOrderRequest
from app.services.ports import TokenIdentityLookup


class OrderService:
    def __init__(
        self, client: OrderClient, deadline: float, identity_lookup: TokenIdentityLookup | None
    ) -> None:
        self.client = client
        self.deadline = deadline
        self.identity_lookup = identity_lookup

    async def _user_id(self, token: str) -> str:
        if self.identity_lookup is None:
            raise HTTPException(status_code=501, detail="Token identity lookup is not configured")
        return await self.identity_lookup.user_id_for_token(token)

    async def create_order(
        self, payload: CreateOrderRequest, token: str, idempotency_key: str
    ) -> dict[str, object]:
        user_id = await self._user_id(token)
        request = self.client.messages.CreateOrderRequest(
            user_id=user_id,
            idempotency_key=idempotency_key,
            items=[
                self.client.messages.OrderItemRequest(**item.model_dump()) for item in payload.items
            ],
            currency=payload.currency,
            shipping_address_json=json.dumps(payload.shipping_address.model_dump()),
        )
        try:
            result = await self.client.orders.CreateOrder(request, timeout=self.deadline)
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}

    async def list_orders(self, token: str, page_size: int, page_token: str) -> dict[str, object]:
        user_id = await self._user_id(token)
        try:
            result = await self.client.orders.ListOrders(
                self.client.messages.ListOrdersRequest(
                    user_id=user_id, page_size=page_size, page_token=page_token
                ),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}

    async def get_order(self, token: str, order_id: str) -> dict[str, object]:
        user_id = await self._user_id(token)
        try:
            result = await self.client.orders.GetOrder(
                self.client.messages.GetOrderRequest(id=order_id, user_id=user_id),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}

    async def cancel_order(self, token: str, order_id: str, note: str) -> dict[str, object]:
        user_id = await self._user_id(token)
        try:
            result = await self.client.orders.CancelOrder(
                self.client.messages.CancelOrderRequest(id=order_id, user_id=user_id, note=note),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}
