"""Environment-backed service configuration."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    auth_grpc_target: str = "localhost:50052"
    commerce_grpc_target: str = "localhost:50062"
    grpc_deadline_seconds: float = Field(default=5.0, gt=0, le=60)
    grpc_tls: bool = False
    grpc_ca_cert: str | None = None
    grpc_client_cert: str | None = None
    grpc_client_key: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    max_request_bytes: int = Field(default=1_048_576, gt=0)
    docs_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, origins: object) -> object:
        if isinstance(origins, str):
            return [origin.strip() for origin in origins.split(",") if origin.strip()]
        return origins

    @model_validator(mode="after")
    def certificate_pair(self) -> "Settings":
        if bool(self.grpc_client_cert) != bool(self.grpc_client_key):
            raise ValueError("GRPC_CLIENT_CERT and GRPC_CLIENT_KEY must be configured together")
        if self.app_env == "production" and not self.grpc_tls:
            raise ValueError("GRPC_TLS must be enabled in production")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not allowed")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
