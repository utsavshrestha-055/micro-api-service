"""FastAPI application factory and shared gRPC lifecycle."""

import contextvars
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import grpc
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.routes import auth, categories, orders, products
from app.clients.auth_client import AuthClient
from app.clients.catalog_client import CatalogClient
from app.clients.order_client import OrderClient
from app.config import Settings, get_settings
from app.services.auth import AuthService
from app.services.catalog import CatalogService
from app.services.orders import OrderService
from app.services.ports import CustomerProvisioning, TokenIdentityLookup

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
logger = logging.getLogger("micro_api")


def _channel(target: str, settings: Settings) -> grpc.aio.Channel:
    interceptors = [_RequestIdInterceptor()]
    if settings.grpc_tls:
        root = Path(settings.grpc_ca_cert).read_bytes() if settings.grpc_ca_cert else None
        cert = Path(settings.grpc_client_cert).read_bytes() if settings.grpc_client_cert else None
        key = Path(settings.grpc_client_key).read_bytes() if settings.grpc_client_key else None
        credentials = grpc.ssl_channel_credentials(
            root_certificates=root, private_key=key, certificate_chain=cert
        )
        return grpc.aio.secure_channel(target, credentials, interceptors=interceptors)
    return grpc.aio.insecure_channel(target, interceptors=interceptors)


class _RequestIdInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    async def intercept_unary_unary(
        self, continuation: Any, client_call_details: grpc.aio.ClientCallDetails, request: Any
    ) -> Any:
        metadata = list(client_call_details.metadata or ())
        metadata.append(("x-request-id", request_id_context.get()))
        details = _ClientCallDetails(
            client_call_details.method,
            client_call_details.timeout,
            metadata,
            client_call_details.credentials,
            client_call_details.wait_for_ready,
        )
        started = time.monotonic()
        call = await continuation(details, request)
        try:
            response = await call
        except grpc.aio.AioRpcError as error:
            logger.info(
                "grpc_call request_id=%s method=%s duration_ms=%.1f status=%s",
                request_id_context.get(),
                client_call_details.method,
                (time.monotonic() - started) * 1000,
                error.code().name,
            )
            raise
        logger.info(
            "grpc_call request_id=%s method=%s duration_ms=%.1f status=OK",
            request_id_context.get(),
            client_call_details.method,
            (time.monotonic() - started) * 1000,
        )
        return response


class _ClientCallDetails(
    grpc.aio.ClientCallDetails,
):
    def __init__(
        self,
        method: str,
        timeout: float | None,
        metadata: Any,
        credentials: grpc.CallCredentials | None,
        wait_for_ready: bool | None,
    ) -> None:
        self.method = method
        self.timeout = timeout
        self.metadata = metadata
        self.credentials = credentials
        self.wait_for_ready = wait_for_ready


class _RequestBodyLimit:
    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        body_size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                messages.append(message)
                break
            body_size += len(message.get("body", b""))
            if body_size > self.limit:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {"type": "http.response.body", "body": b'{"detail":"Request too large"}'}
                )
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)


def create_app(
    settings: Settings | None = None,
    *,
    identity_lookup: TokenIdentityLookup | None = None,
    customer_provisioning: CustomerProvisioning | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    logging.basicConfig(level=active_settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        auth_channel = _channel(active_settings.auth_grpc_target, active_settings)
        product_channel = _channel(active_settings.commerce_grpc_target, active_settings)
        application.state.auth_channel = auth_channel
        application.state.product_channel = product_channel
        auth_client = AuthClient(auth_channel)
        catalog_client = CatalogClient(product_channel)
        order_client = OrderClient(product_channel)
        application.state.auth_service = AuthService(
            auth_client,
            active_settings.grpc_deadline_seconds,
            identity_lookup,
            customer_provisioning,
        )
        application.state.catalog_service = CatalogService(
            catalog_client, active_settings.grpc_deadline_seconds
        )
        application.state.order_service = OrderService(
            order_client, active_settings.grpc_deadline_seconds, identity_lookup
        )
        try:
            yield
        finally:
            await auth_channel.close()
            await product_channel.close()

    docs = active_settings.docs_enabled and active_settings.app_env != "production"
    application = FastAPI(
        title="Commerce API Gateway",
        version="1.0.0",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.identity_lookup = identity_lookup
    application.state.customer_provisioning = customer_provisioning
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(_RequestBodyLimit, limit=active_settings.max_request_bytes)

    @application.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if supplied_request_id.isascii()
            and supplied_request_id
            and len(supplied_request_id) <= 128
            and all(character.isalnum() or character in "._:-" for character in supplied_request_id)
            else str(uuid.uuid4())
        )
        token = request_id_context.set(request_id)
        started = time.monotonic()
        try:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > active_settings.max_request_bytes:
                response: Response = JSONResponse(
                    status_code=413, content={"detail": "Request too large"}
                )
            else:
                response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request request_id=%s method=%s route=%s duration_ms=%.1f status=%s",
            request_id,
            request.method,
            request.url.path,
            (time.monotonic() - started) * 1000,
            response.status_code,
        )
        return response

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"], response_model=None)
    async def readiness(request: Request) -> Any:
        auth_channel = getattr(request.app.state, "auth_channel", None)
        product_channel = getattr(request.app.state, "product_channel", None)
        if auth_channel is None or product_channel is None:
            return JSONResponse(status_code=503, content={"detail": "Dependencies unavailable"})
        auth_channel.get_state(try_to_connect=True)
        product_channel.get_state(try_to_connect=True)
        if (
            auth_channel.get_state() != grpc.ChannelConnectivity.READY
            or product_channel.get_state() != grpc.ChannelConnectivity.READY
        ):
            return JSONResponse(status_code=503, content={"detail": "Dependencies unavailable"})
        return {"status": "ok"}

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(categories.router)
    api.include_router(products.router)
    api.include_router(orders.router)
    application.include_router(api)
    return application


app = create_app()
