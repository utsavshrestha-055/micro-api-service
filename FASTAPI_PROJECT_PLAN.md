# FastAPI Gateway Project Plan

## Goal

Add a FastAPI HTTP gateway for the Next.js storefront. The browser communicates with this gateway using ordinary JSON over HTTP(S). The gateway communicates with `auth-service` and `micro-product-service` using their gRPC APIs.

The gateway is an adapter and policy enforcement point. It does not own users, roles, permissions, product data, orders, addresses, or an application database. It does not create roles or permissions. Those access definitions are provisioned and maintained through `admin-service`.

## Service boundaries

```text
Next.js storefront
      | HTTPS + JSON, bearer token
      v
FastAPI API gateway
      | gRPC                    | gRPC
      v                         v
auth-service              micro-product-service
AuthenticationService     CategoryService
AuthorizationService      ProductService
                           ProductImageService
                           OrderService
```

### Ownership

| Component | Owns |
| --- | --- |
| FastAPI gateway | HTTP routes, input validation, JSON response contract, permission checks before downstream calls, caller identity propagation, HTTP error mapping |
| auth-service | Generic users, passwords, sessions, role and permission storage, role assignments, permission evaluation; it has no customer or administrator-specific registration policy |
| micro-product-service | Catalog, product images, inventory effects, orders, order ownership enforcement |
| admin-service | Application role/permission definitions and seeding, administrator UI for access management, customer-role assignment orchestration |
| Next.js frontend | Presentation and bearer-token transport; it is never an authority for user ID, price, stock, role, or permission |

The auth service remains generic. It must not learn about a `customer` role, storefront registration policy, FastAPI, or administrator-specific workflows. The admin service defines the application’s `customer` role and permissions using the existing authorization gRPC API.

## Existing repository findings

- The frontend currently uses mock implementations in `frontend/lib/services/index.ts`.
- Frontend types are in `frontend/types/index.ts`; its mock product shape has display fields that are not present in `catalog.proto`.
- `auth-service/proto/auth.proto` defines generic registration, login, logout, and `AuthorizationService.CheckPermission` operations. Registration may assign the generic `user` role if that role exists; no customer-specific logic should be added there.
- `micro-product-service` exposes catalog and order gRPC APIs. Its README says it trusts callers and does not perform permission checks.
- `orders.OrderService.GetOrder`, `ListOrders`, and `CancelOrder` scope by both order ID and user ID. Admin order RPCs do not authorize callers.
- `admin-service` already checks individual permissions through `PermissionAuthorizationService` and `EnsurePermission`, and has role and permission synchronization flows.

## FastAPI project layout

```text
micro-api-service/
  app/
    main.py                    # app setup, lifespan, CORS, health/readiness
    config.py                  # env-backed service endpoints, deadlines, TLS
    api/
      dependencies.py          # bearer session and required permission
      errors.py                # gRPC status to HTTP problem response
      routes/
        auth.py
        categories.py
        products.py
        orders.py
    clients/
      auth_client.py           # AuthenticationService and AuthorizationService
      catalog_client.py        # Category, Product, ProductImage clients
      order_client.py
    schemas/
      auth.py
      catalog.py
      orders.py
    services/
      auth.py                  # HTTP/gRPC contract adaptation
      catalog.py
      orders.py
  proto/                       # pinned copies of upstream protobuf contracts
  tests/
  requirements.txt or pyproject.toml
  .env.example
  README.md
```

Keep routers focused on HTTP and validation. Put protobuf construction, mapping, and RPC calls in clients/services. Create shared async gRPC channels at application startup, close them at shutdown, configure a deadline for every call, and add request IDs to HTTP and gRPC logs. Generate stubs from the checked-in service protobuf files; regenerate them when upstream contracts change.

## HTTP contract

- Prefix routes with `/api/v1`.
- Accept and return JSON. A consistent response envelope is `{ "data": ... }`; errors use `{ "detail": "..." }` and the matching HTTP status.
- Protected routes receive `Authorization: Bearer <opaque-auth-service-session-token>`.
- Use Pydantic schemas for body validation, pagination bounds, string lengths, IDs, and quantity limits.
- Do not accept client-supplied roles, user IDs, price totals, stock values, or permission names as authority-bearing inputs.
- Preserve the catalog/order service’s integer minor-unit representation for money. Convert only at the frontend boundary if the UI continues to display decimal currency.

## Permission policy

Every authenticated action calls `AuthorizationService.CheckPermission` for that route’s exact permission before making a product/order call. Do not authorize from a role name, frontend state, or a cached gateway decision. The auth service’s permission check also validates the session and active account.

Follow the admin-service middleware behavior: missing or invalid session is HTTP 401; a valid session without the named permission is HTTP 403; an authorization-service transport failure is HTTP 503. Translate downstream gRPC statuses to stable HTTP statuses and do not expose internal exception details.

| Route/action | Permission | Downstream RPC |
| --- | --- | --- |
| `GET /api/v1/categories` | `categories.read` | `CategoryService.ListCategories` |
| `GET /api/v1/products` | `products.read` | `ProductService.ListProducts` |
| `GET /api/v1/products/{product_id}` | `products.read` | `ProductService.GetProductPage` |
| `POST /api/v1/orders` | `orders.create` | `OrderService.CreateOrder` |
| `GET /api/v1/orders` | `orders.read` | `OrderService.ListOrders` |
| `GET /api/v1/orders/{order_id}` | `orders.read` | `OrderService.GetOrder` |
| `POST /api/v1/orders/{order_id}/cancel` | `orders.cancel` | `OrderService.CancelOrder` |
| `POST /api/v1/auth/register` | Public registration operation | Private admin-service customer-provisioning capability |
| `POST /api/v1/auth/login` | Public authentication operation | `AuthenticationService.Login` |
| `POST /api/v1/auth/logout` | Valid session | `AuthenticationService.Logout` |
| `GET /api/v1/auth/me` | Valid session | Requires a token-bound current-user lookup |

Registration and login are the only public operations because the caller has no session yet. Registration delegates account creation and assignment of the already-seeded customer role to the private admin-service provisioning capability; FastAPI does not create roles or permissions. Login calls auth-service directly. Logout validates and revokes the session. If policy requires a named permission even for logout, introduce a generic account-session permission in the admin catalog; do not encode a customer exception in auth-service.

Future administrator gateway routes must use administrator permissions such as `products.create`, `products.update`, `products.delete`, `categories.create`, `categories.update`, `categories.delete`, `orders.view_all`, and `orders.update`. Only those routes may call `GetOrderAdmin`, `ListOrdersAdmin`, or `UpdateOrderStatus`.

## Customer role and permissions

`admin-service` owns the application access definitions. The existing **Sync application permissions** action creates or updates the customer permission definitions. The existing **Sync application roles** action creates or activates the `customer` role and reconciles its grants to the following least-privilege set:

| Permission | Capability |
| --- | --- |
| `products.read` | Browse storefront products |
| `categories.read` | Browse storefront categories |
| `orders.read` | View orders through customer-scoped RPCs |
| `orders.create` | Submit a customer order |
| `orders.cancel` | Cancel an eligible order owned by the customer |

The role sync should reconcile the role’s grants to exactly this set, removing unexpected extra grants as well as adding missing ones. Run **Sync application permissions** before **Sync application roles**. The role sync requires an administrator authorized for both `roles.manage` and `permissions.manage`. These are admin-service operations, not FastAPI startup actions or API requests.

The ordinary permission catalog sync must also include `orders.create` and `orders.cancel` so those permission definitions remain managed alongside the other application permissions.

## Customer creation and registration flow

### Admin-service operator creation

The existing admin user creation form should create an auth-service account, then use the logged-in administrator’s authorized token to assign the already-seeded `customer` role. It should remove any other default role assignments from that new account so that effective access is limited to the customer role. This requires `users.create`, `users.read`, and `roles.assign` on the admin route. The auth-service-created session token must be revoked after provisioning and must never be returned to the administrator’s browser.

The customer-role sync must be run before account creation. If assignment fails after registration, report that the account exists but its customer access needs repair; do not claim that provisioning succeeded. Re-running role synchronization is safe. Role assignment is multiple gRPC operations, not an atomic transaction, so the admin UI must make partial failure visible.

### Storefront self-registration

FastAPI must not create a role or permission and must not possess a superadmin token. A newly registered user cannot assign its own `customer` role because `AssignRole` requires `roles.assign`. Therefore public registration needs a trusted provisioning boundary separate from the public gateway:

1. The browser submits email, password, and profile basics to FastAPI.
2. FastAPI delegates provisioning to a private admin-service customer-provisioning operation.
3. Admin-service registers the generic auth-service user, assigns the pre-existing `customer` role using a narrowly privileged service identity, removes any generic default role, and handles/revokes temporary tokens.
4. FastAPI returns the normal JSON session response only after provisioning succeeds.

Protect this internal admin-service operation with private network access plus mTLS or an equivalent service credential, strict rate limiting, input validation, and audit logs. Do not expose the privileged assignment credential to the browser or configure a superadmin credential in FastAPI. If the current admin-service deployment cannot safely host such a service identity, implement a dedicated narrowly scoped provisioning identity/capability before enabling public self-registration. Do not solve the gap by adding customer-specific behavior to auth-service.

## Identity and order ownership

The current auth protobuf does not provide the user ID associated with a session token. Do not accept `user_id` from the browser. Before implementing `/auth/me` or customer order routes, add a generic token-bound identity lookup capability to the auth boundary, or return an identity proof from a trusted registration/login flow that the gateway can validate server-side.

After resolving identity, the gateway supplies that ID to `CreateOrder`, `ListOrders`, `GetOrder`, and `CancelOrder`. The order service’s customer RPCs must enforce ownership. Never route a customer request through admin order RPCs.

## Frontend mapping and known contract gaps

Replace the mocked methods in `frontend/lib/services/index.ts` with `fetch` adapters that use the API base URL and bearer token. Cover categories, product list/search/detail, login/register/logout, current profile, order list/detail, checkout, and cancellation. Keep auth tokens out of URLs and logs; choose a token storage strategy with the frontend’s XSS/session requirements in mind.

The existing UI expects product values such as `rating`, `reviewCount`, `colors`, `images`, dollar prices, payment status, and a customer address/profile model. The catalog protobuf only provides catalog product fields, product details, and image metadata; the order protobuf has status, total, items, and a JSON shipping address. There is no customer profile/address service in the scanned services. Agree on a versioned JSON mapping and update frontend types, or add the missing backend capabilities before claiming those UI fields persist. Do not return submitted profile/address values as if they were stored.

For checkout, send product IDs and quantities plus shipping address and an `Idempotency-Key`. The order service calculates price, stock, and totals. The client’s displayed total is informational only. The frontend should reuse the idempotency key if it retries the same checkout.

## Configuration and operations

Use environment settings for auth and commerce gRPC targets, deadlines, TLS trust roots/client certificates, CORS origins, request size limits, and environment mode. Keep gRPC private and use TLS/mTLS in deployed environments. Use an explicit frontend origin allowlist; never use wildcard CORS with credentials.

Apply ingress rate limits to login, registration, and checkout. Log request ID, route, RPC method, duration, and status. Never log passwords, bearer tokens, raw authorization headers, or shipping-address JSON. Provide liveness and dependency-aware readiness separately. Restrict Swagger/OpenAPI exposure as appropriate for production.

## Delivery sequence

1. Use the permissions tab’s existing sync action to seed the permission definitions, then use the roles tab’s existing sync action to ensure the active customer role has exactly the five grants above.
2. Update admin-service user creation to assign only the customer role and require the corresponding admin permissions.
3. Design and secure the private self-registration provisioning capability and generic token-to-user identity lookup.
4. Create the FastAPI project and generated async gRPC clients from the checked-in auth, catalog, and orders protobufs.
5. Implement HTTP schemas, shared gRPC error mapping, and permission dependencies.
6. Add catalog and customer order routes; ensure customer IDs come only from verified identity and use customer-scoped RPCs.
7. Implement login, logout, profile identity, and customer registration orchestration.
8. Replace frontend mocks, align frontend types with real service capabilities, and document environment setup.
9. Verify the permission matrix, owner isolation, retry/idempotency behavior, error mapping, and gRPC-unavailable behavior before deployment.

## Acceptance criteria

- FastAPI uses JSON/HTTP at its public boundary and gRPC for service-to-service calls.
- Every authenticated operation checks its permission with auth-service before calling a downstream service.
- FastAPI creates no role or permission and carries no administrator/superadmin access token.
- Admin-service can idempotently seed an active `customer` role with exactly the least-privilege storefront grants.
- Admin-service-created customer accounts receive only the seeded customer role; provisioning failures are reported as partial failures.
- Customer order RPCs always use the identity resolved from the caller’s token, and admin RPCs are never exposed to customer routes.
- The frontend receives normal JSON responses and does not treat mock-only data as persisted backend data.
