"""Catalog query validation."""

from pydantic import BaseModel, ConfigDict, Field


class ProductQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(default=20, ge=1, le=100)
    page_token: str = Field(default="", max_length=2048)
    category_id: str = Field(default="", max_length=128)
    name_search: str = Field(default="", max_length=200)
    min_price_minor: int | None = Field(default=None, ge=0)
    max_price_minor: int | None = Field(default=None, ge=0)


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(default=20, ge=1, le=100)
    page_token: str = Field(default="", max_length=2048)
