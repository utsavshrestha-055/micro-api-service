"""HTTP boundary tests which do not require running downstream services."""

from types import SimpleNamespace
from typing import Any, cast

import grpc
from fastapi.testclient import TestClient

from app.clients.auth_client import AuthClient
from app.clients.order_client import OrderClient
from app.config import Settings
from app.generated import orders_pb2
from app.main import create_app
from app.schemas.orders import CreateOrderRequest
from app.services.auth import AuthService
from app.services.orders import OrderService


class PermissionService:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.last_request: Any = None

    async def check_permission(self, token: str, permission: str) -> None:
        self.last_request = SimpleNamespace(access_token=token, permission=permission)
        if not self.allowed:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Permission denied")


def add_permission_service(app: Any, allowed: bool) -> PermissionService:
    service = PermissionService(allowed)
    app.state.auth_service = service
    return service


def test_liveness_is_independent_of_downstreams() -> None:
    client = TestClient(create_app(Settings()))
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("x-request-id")


def test_production_tls_does_not_require_client_certificates() -> None:
    settings = Settings(
        app_env="production",
        grpc_tls=True,
        grpc_ca_cert="",
        grpc_client_cert="",
        grpc_client_key="",
    )
    assert settings.grpc_tls
    assert not settings.grpc_ca_cert
    assert not settings.grpc_client_cert
    assert not settings.grpc_client_key


def test_cors_origins_accept_comma_separated_environment_format() -> None:
    settings = Settings(cors_origins="https://store.example.com,https://admin.example.com")
    assert settings.cors_origins == [
        "https://store.example.com",
        "https://admin.example.com",
    ]


def test_registration_reports_unimplemented_private_provisioning() -> None:
    app = create_app(Settings())
    app.state.auth_service = AuthService(cast(AuthClient, None), 5, None, None)
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "password": "secret-password",
            "first_name": "A",
            "last_name": "B",
        },
    )
    assert response.status_code == 501
    assert response.json() == {"detail": "Customer provisioning is not configured"}


def test_login_hides_grpc_unavailable_details() -> None:
    app = create_app(Settings())

    class AuthenticationService:
        async def Login(self, *_args: Any, **_kwargs: Any) -> Any:
            raise grpc.aio.AioRpcError(
                grpc.StatusCode.UNAVAILABLE, details="internal endpoint detail"
            )

    app.state.auth_service = AuthService(
        cast(
            AuthClient,
            SimpleNamespace(
                messages=SimpleNamespace(LoginRequest=lambda **values: SimpleNamespace(**values)),
                authentication=AuthenticationService(),
            ),
        ),
        5,
        None,
        None,
    )
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "customer@example.com", "password": "secret-password"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}


def test_me_requires_bearer_session_before_identity_lookup() -> None:
    client = TestClient(create_app(Settings()))
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_request_body_limit_applies_to_requests_without_content_length() -> None:
    client = TestClient(create_app(Settings(max_request_bytes=16)))
    response = client.post("/api/v1/auth/login", content=b"x" * 17)
    assert response.status_code == 413


def test_identity_route_reports_missing_capability() -> None:
    app = create_app(Settings())
    app.state.auth_service = AuthService(cast(AuthClient, None), 5, None, None)
    client = TestClient(app)
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer opaque"})
    assert response.status_code == 501


def test_category_permission_is_checked_before_downstream_call() -> None:
    app = create_app(Settings())
    permissions = add_permission_service(app, allowed=False)
    response = TestClient(app).get("/api/v1/categories", headers={"Authorization": "Bearer opaque"})
    assert response.status_code == 403
    assert permissions.last_request.permission == "categories.read"
    assert permissions.last_request.access_token == "opaque"


def test_customer_order_route_stops_at_missing_identity_port() -> None:
    app = create_app(Settings())
    permissions = add_permission_service(app, allowed=True)
    app.state.order_service = OrderService(cast(OrderClient, None), 5, None)
    response = TestClient(app).get(
        "/api/v1/orders/order-1", headers={"Authorization": "Bearer opaque"}
    )
    assert response.status_code == 501
    assert permissions.last_request.permission == "orders.read"


def test_customer_order_uses_identity_port_user_id() -> None:
    app = create_app(Settings())
    permissions = add_permission_service(app, allowed=True)

    class Identity:
        token: str | None = None

        async def user_id_for_token(self, token: str) -> str:
            self.token = token
            return "verified-user-id"

    class OrderRpc:
        request: Any = None

        async def GetOrder(self, request: Any, **_kwargs: Any) -> Any:
            self.request = request
            return orders_pb2.OrderResponse(  # type: ignore[attr-defined]
                order=orders_pb2.Order(  # type: ignore[attr-defined]
                    id=request.id, user_id=request.user_id
                )
            )

    identity = Identity()
    rpc = OrderRpc()
    app.state.order_service = OrderService(
        cast(OrderClient, SimpleNamespace(messages=orders_pb2, orders=rpc)), 5, identity
    )
    response = TestClient(app).get(
        "/api/v1/orders/order-1", headers={"Authorization": "Bearer opaque"}
    )
    assert response.status_code == 200
    assert permissions.last_request.permission == "orders.read"
    assert identity.token == "opaque"
    assert rpc.request.id == "order-1"
    assert rpc.request.user_id == "verified-user-id"
    assert response.json()["data"]["order"]["user_id"] == "verified-user-id"


def test_order_body_rejects_authority_fields_and_invalid_quantity() -> None:
    body: dict[str, Any] = {
        "items": [{"product_id": "p-1", "quantity": 1}],
        "shipping_address": {
            "name": "A B",
            "line1": "1 Main",
            "city": "City",
            "postal_code": "1",
            "country_code": "US",
        },
        "currency": "USD",
        "user_id": "browser-controlled",
    }
    try:
        CreateOrderRequest.model_validate(body)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown user_id field must be rejected")
    body.pop("user_id")
    body["items"][0]["quantity"] = 0
    try:
        CreateOrderRequest.model_validate(body)
    except ValueError:
        pass
    else:
        raise AssertionError("non-positive item quantity must be rejected")
