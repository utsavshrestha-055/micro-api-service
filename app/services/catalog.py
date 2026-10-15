"""Catalog protobuf construction, RPC calls and JSON mapping."""

import grpc
from google.protobuf.json_format import MessageToDict

from app.api.errors import grpc_http_error
from app.clients.catalog_client import CatalogClient
from app.schemas.catalog import PageQuery, ProductQuery


class CatalogService:
    def __init__(self, client: CatalogClient, deadline: float) -> None:
        self.client = client
        self.deadline = deadline

    async def list_categories(self, page: PageQuery) -> dict[str, object]:
        try:
            result = await self.client.categories.ListCategories(
                self.client.messages.PageRequest(
                    page_size=page.page_size, page_token=page.page_token
                ),
                timeout=self.deadline,
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}

    async def list_products(self, query: ProductQuery) -> dict[str, object]:
        args: dict[str, object] = {
            "page_size": query.page_size,
            "page_token": query.page_token,
            "category_id": query.category_id,
            "name_search": query.name_search,
        }
        if query.min_price_minor is not None:
            args["min_price_minor"] = query.min_price_minor
        if query.max_price_minor is not None:
            args["max_price_minor"] = query.max_price_minor
        try:
            result = await self.client.products.ListProducts(
                self.client.messages.ProductListRequest(**args), timeout=self.deadline
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}

    async def get_product(self, product_id: str) -> dict[str, object]:
        try:
            result = await self.client.products.GetProductPage(
                self.client.messages.ProductId(id=product_id), timeout=self.deadline
            )
        except grpc.aio.AioRpcError as error:
            raise grpc_http_error(error) from None
        return {"data": MessageToDict(result, preserving_proto_field_name=True)}
