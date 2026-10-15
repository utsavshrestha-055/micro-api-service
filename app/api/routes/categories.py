"""Customer category routes."""

from typing import cast

from fastapi import APIRouter, Depends, Request

from app.schemas.catalog import PageQuery
from app.services.catalog import CatalogService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(
    request: Request,
    page: PageQuery = Depends(),
) -> dict[str, object]:
    return await cast(CatalogService, request.app.state.catalog_service).list_categories(page)
