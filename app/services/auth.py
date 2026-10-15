"""HTTP and gRPC adaptation for authentication and authorization."""

import grpc
from fastapi import HTTPException
from google.protobuf.json_format import MessageToDict

from app.api.errors import grpc_http_error
from app.clients.auth_client import AuthClient
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.ports import CustomerProvisioning, TokenIdentityLookup


class AuthService:
    def __init__(
        self,
        client: AuthClient,
        deadline: float,
        identity_lookup: TokenIdentityLookup | None,
        customer_provisioning: CustomerProvisioning | None,
    ) -> None:
        self.client = client
        self.deadline = deadline
        self.identity_lookup = identity_lookup
        self.customer_provisioning = customer_provisioning

    async def login(self, payload: LoginRequest) -> dict[str, object]:
        try:
            response = await self.client.authentication.Login(
                self.client.messages.LoginRequest(
                    email=str(payload.email), password=payload.password
                ),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(response, preserving_proto_field_name=True)}

    async def logout(self, token: str) -> dict[str, object]:
        try:
            result = await self.client.authentication.Logout(
                self.client.messages.AccessTokenRequest(access_token=token),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error, authorization=True) from None
        return {"data": {"success": result.success}}

    async def check_permission(self, token: str, permission: str) -> None:
        try:
            response = await self.client.authorization.CheckPermission(
                self.client.messages.CheckPermissionRequest(
                    access_token=token, permission=permission
                ),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error, authorization=True) from None
        if not response.allowed:
            raise HTTPException(status_code=403, detail="Permission denied")

    async def register(self, payload: RegisterRequest) -> dict[str, object]:
        if self.customer_provisioning is None:
            raise HTTPException(status_code=501, detail="Customer provisioning is not configured")
        result = await self.customer_provisioning.register_customer(
            str(payload.email), payload.password, payload.first_name, payload.last_name
        )
        return {"data": result}

    async def current_user(self, token: str) -> dict[str, object]:
        if self.identity_lookup is None:
            raise HTTPException(status_code=501, detail="Token identity lookup is not configured")
        user_id = await self.identity_lookup.user_id_for_token(token)
        return {"data": {"id": user_id}}
