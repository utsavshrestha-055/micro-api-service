"""Authentication request schemas."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictRequest):
    email: EmailStr
    password: Annotated[
        str, StringConstraints(min_length=1, max_length=256, strip_whitespace=False)
    ]


class RegisterRequest(LoginRequest):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
