"""Explicit integration ports for capabilities absent from checked-in contracts."""

from typing import Protocol


class TokenIdentityLookup(Protocol):
    async def user_id_for_token(self, token: str) -> str: ...


class CustomerProvisioning(Protocol):
    async def register_customer(
        self, email: str, password: str, first_name: str, last_name: str
    ) -> dict[str, object]: ...
