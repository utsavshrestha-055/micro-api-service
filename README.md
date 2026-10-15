# Commerce API Gateway

FastAPI gateway for storefront JSON/HTTP requests. It owns no users, permissions, catalog data, orders, or database state. It checks every protected storefront permission through `AuthorizationService.CheckPermission` before making a catalog or order RPC.

## Local setup

Requires Python 3.11 or newer. The checked-in async gRPC clients are generated from the pinned files under `proto/`.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
make verify
make run
```

The gateway listens on port 8000. Liveness is `GET /health/live`; dependency readiness is `GET /health/ready`. Development API documentation is at `/docs`. Production disables docs and requires gRPC TLS.

See [HostMe.md](HostMe.md) for local platform setup and Linux production hosting steps.

When an upstream proto changes, update only its pinned copy after reviewing the upstream contract, then run:

```sh
make generate
make verify
```

`AUTH_GRPC_TARGET` and `PRODUCT_GRPC_TARGET` use the service targets configured for admin-service (local defaults `localhost:50052` and `localhost:50062`). TLS can use a CA and an optional client certificate/key pair. The gateway uses a deadline for every RPC. Request IDs are forwarded as gRPC metadata and included with route/RPC duration and status logs; credentials, passwords, and shipping-address content are not logged.

Configure `CORS_ORIGINS` as a comma-separated allowlist. Request body size is capped by `MAX_REQUEST_BYTES`; deployments should also enforce an ingress body limit. Login, registration, and checkout need ingress rate limits. gRPC endpoints should remain private.

## Routes

All application routes are under `/api/v1`. Successful responses use `{ "data": ... }`; errors use `{ "detail": ... }`.

| Route | Permission | RPC |
| --- | --- | --- |
| `POST /auth/login` | Public | `AuthenticationService.Login` |
| `POST /auth/logout` | Valid session | `AuthenticationService.Logout` |
| `POST /auth/register` | Public | Private admin provisioning port; currently 501 |
| `GET /auth/me` | Valid session | Token identity port; currently 501 |
| `GET /categories` | `categories.read` | `CategoryService.ListCategories` |
| `GET /products` | `products.read` | `ProductService.ListProducts` |
| `GET /products/{product_id}` | `products.read` | `ProductService.GetProductPage` |
| `POST /orders` | `orders.create` | `OrderService.CreateOrder` |
| `GET /orders` | `orders.read` | `OrderService.ListOrders` |
| `GET /orders/{order_id}` | `orders.read` | `OrderService.GetOrder` |
| `POST /orders/{order_id}/cancel` | `orders.cancel` | `OrderService.CancelOrder` |

Catalog, product, order and logout endpoints require `Authorization: Bearer <token>`. Checkout accepts product IDs, quantities, a shipping address and `Idempotency-Key`; it never accepts user IDs, prices or totals. The order service calculates prices and totals. Only customer-scoped order RPCs are wired; admin order RPCs are not exposed.

## Open items and blockers

- **Token-to-user identity lookup:** `auth.proto` has no operation that resolves an opaque session token to its user ID. `TokenIdentityLookup` is the port; `/auth/me` and customer order routes return 501 until a trusted adapter is provided. No request-supplied user ID is used.
- **Private admin-service provisioning for self-registration:** the current contracts have no narrowly scoped private customer provisioning operation. `CustomerProvisioning` is the port; registration returns 501 until a real adapter delegates account creation and seeded customer-role assignment to admin-service. The gateway has no privileged role-assignment token.
- Admin-service permission/role seeding and operator account-creation changes are outside this folder and were not modified.
- Frontend mocks and types are outside this folder and were not modified.
- Production ingress rate limits, private service networking, and deployed TLS certificate provisioning must be configured by deployment infrastructure.
- The checked-in auth and product gRPC servers currently start without TLS configuration. Enable server-side TLS on both services before running this gateway in production, where `GRPC_TLS=true` is required.
- Product profile fields such as ratings, review counts, colors and customer addresses have no persistence API in the scanned contracts; this gateway does not claim to persist them.

## Decisions

- Proto copies are pinned under `proto/` and generated stubs are checked in so runtime does not require a compiler.
- JSON preserves protobuf field names and integer minor currency units.
- Shipping address JSON is versioned by the gateway's v1 route and currently consists of `name`, `line1`, `line2`, `city`, `region`, `postal_code`, and ISO 3166-1 alpha-2 `country_code`; the order service stores the serialized JSON without a schema of its own.
- Checkout currency defaults to `USD` because the order proto requires a currency string but defines no default or currency enum; callers may submit a three-letter currency code.
- Readiness checks gRPC channel connectivity because only auth exposes a health RPC and the commerce contracts define no health service.
- Rate limiting is delegated to ingress so limits work across multiple gateway processes; the application does not use a per-process counter.
- Plan steps that require admin-service and frontend changes remain pending because this work is restricted to `micro-api-service`.
