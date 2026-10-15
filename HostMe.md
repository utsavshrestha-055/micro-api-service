# Run and host the Commerce API Gateway

This guide covers local development and production hosting for `micro-api-service`. The public interface is FastAPI over HTTPS/JSON. The gateway calls the auth service and product/commerce service over gRPC; the host must be able to reach both endpoints. It has no database or background worker.

## Requirements

- Python 3.11 or newer. The project has been built and verified with Python 3.14.
- Network access from the gateway host to the auth and product-service gRPC endpoints.
- HTTPS termination at a trusted ingress, load balancer, or reverse proxy for hosted environments.
- TLS trust roots for deployed gRPC connections. Configure a client certificate and key too when the services require mutual TLS.
- Ingress request-size limits and distributed rate limits for login, registration, and checkout.

Generated protobuf clients are checked in under `app/generated`; a production host does not need `protoc` or `grpcio-tools`. It does need outbound access to install the Python packages on first setup, or an internally built wheel/image containing them.

## Local development

Create a virtual environment and install the development tools:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
make verify
make run
```

The service listens on `http://localhost:8000`. The sample environment uses local plaintext gRPC targets. Change `AUTH_GRPC_TARGET` and `COMMERCE_GRPC_TARGET` to reachable service endpoints. For local browser work, set `CORS_ORIGINS` to the exact storefront origin, such as `http://localhost:3000`.

On Windows PowerShell, use the platform-specific virtual-environment commands:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Linux production host

### 1. Prepare the host and release

Use a supported Linux distribution, a dedicated unprivileged account, and a release directory such as `/opt/micro-api-service/current`. Install Python 3.11 or newer and `python3-venv`. Keep the service process bound to loopback or a private interface; expose it to the browser only through an HTTPS ingress.

From the release directory, create the runtime environment and install production dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
```

Run `make verify` in CI or the release build before promoting a release. Development dependencies are not needed on the production host.

### 2. Configure the environment and certificates

Store runtime settings in a host-managed environment file, for example `/etc/micro-api-service.env`. Do not commit it. A production configuration should resemble:

```dotenv
APP_ENV=production
LOG_LEVEL=INFO
AUTH_GRPC_TARGET=auth.internal.example:50052
COMMERCE_GRPC_TARGET=product.internal.example:50062
GRPC_DEADLINE_SECONDS=5
GRPC_TLS=true
GRPC_CA_CERT=/run/secrets/services-ca.pem
GRPC_CLIENT_CERT=/run/secrets/micro-api-service.pem
GRPC_CLIENT_KEY=/run/secrets/micro-api-service-key.pem
CORS_ORIGINS=https://store.example.com
MAX_REQUEST_BYTES=1048576
DOCS_ENABLED=false
```

Use the private DNS names and ports for your deployment. `GRPC_CLIENT_CERT` and `GRPC_CLIENT_KEY` must either both be set or both be empty. If service TLS does not require mutual TLS, omit both client settings. Ensure the service account can read the CA and optional client credentials, but no other account can read the private key. The gateway enforces gRPC TLS when `APP_ENV=production` and refuses wildcard CORS origins.

The environment variable names mirror the host/timeout/TLS pattern used by admin-service (`AUTH_GRPC_HOST`, `COMMERCE_GRPC_HOST`, and corresponding TLS settings); this gateway uses `*_TARGET`, one shared deadline, and shared certificate settings for its two channels.

### 3. Run under systemd

Create `/etc/systemd/system/micro-api-service.service` and adjust the account and paths to your release layout:

```ini
[Unit]
Description=Commerce API Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=micro-api
Group=micro-api
WorkingDirectory=/opt/micro-api-service/current
EnvironmentFile=/etc/micro-api-service.env
ExecStart=/opt/micro-api-service/current/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

If you use a different worker count, size it for the host and downstream gRPC services. Each worker owns its own gRPC channels. After installing the unit:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now micro-api-service
sudo systemctl status micro-api-service
journalctl -u micro-api-service -f
```

The application logs to standard output. Logs include request ID, route/RPC method, duration, and status; they exclude passwords, bearer tokens, raw authorization headers, and shipping-address JSON.

### 4. Put an HTTPS ingress in front

Terminate browser HTTPS at a trusted load balancer or reverse proxy and forward requests to `127.0.0.1:8000`. Set the ingress request-body limit to match `MAX_REQUEST_BYTES` and apply distributed rate limits to:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- `POST /api/v1/orders`

Keep port 8000 private. Do not expose either gRPC endpoint publicly. Pass a safe `X-Request-ID` to the app if the ingress supplies one; otherwise the app generates one. Allow the storefront origin in `CORS_ORIGINS` exactly, including scheme and port. Do not enable wildcard origins.

### 5. Verify the deployment

Check liveness and dependency-aware readiness through the private ingress or from the host:

```sh
curl -fsS http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
```

Readiness returns 200 once both gRPC channels connect. It returns 503 while either dependency is unavailable. Confirm the service logs show successful downstream connectivity, then test a protected catalog route with a valid bearer token and verify the auth service records its permission check before the catalog call. Production docs/OpenAPI are disabled.

## Current deployment limits

- `/api/v1/auth/register` returns 501 until a trusted private admin-service provisioning adapter exists.
- `/api/v1/auth/me` and customer order routes return 501 until a trusted token-to-user identity adapter exists. Do not work around this by accepting a browser-supplied user ID.
- Do not advertise checkout, order history, or self-registration as available storefront capabilities until those adapters are implemented and verified against the deployed services.
- Admin permission/role seeding and frontend wiring are separate deployment tasks; see [README.md](README.md#open-items-and-blockers).
- Apply ingress limits, service-network policy, HTTPS certificates, and gRPC CA/client credentials through your platform's secret and network management.
