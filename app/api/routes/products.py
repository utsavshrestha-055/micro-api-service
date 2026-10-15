"""Customer product routes."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.schemas.catalog import ProductQuery
from app.services.catalog import CatalogService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
async def list_products(
    request: Request,
    query: ProductQuery = Depends(),
) -> dict[str, object]:
    if query.min_price_minor is not None and query.max_price_minor is not None:
        if query.min_price_minor > query.max_price_minor:
            raise HTTPException(status_code=422, detail="Minimum price must not exceed maximum")
    return await cast(CatalogService, request.app.state.catalog_service).list_products(query)


@router.get("/{product_id}")
async def get_product(
    request: Request,
    product_id: str = Path(..., min_length=1, max_length=128),
) -> dict[str, object]:
    return await cast(CatalogService, request.app.state.catalog_service).get_product(product_id)
