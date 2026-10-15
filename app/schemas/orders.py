"""Customer order input validation."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OrderItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=128)
    quantity: int = Field(ge=1, le=1000)


class ShippingAddress(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    line1: str = Field(min_length=1, max_length=200)
    line2: str = Field(default="", max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str = Field(default="", max_length=100)
    postal_code: str = Field(min_length=1, max_length=32)
    country_code: str = Field(min_length=2, max_length=2, pattern="^[A-Z]{2}$")


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[OrderItemInput], Field(min_length=1, max_length=100)]
    shipping_address: ShippingAddress
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern="^[A-Z]{3}$")
