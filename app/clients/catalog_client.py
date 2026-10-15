"""Catalog gRPC client."""

import grpc

from app.generated import catalog_pb2, catalog_pb2_grpc


class CatalogClient:
    def __init__(self, channel: grpc.aio.Channel) -> None:
        self.messages = catalog_pb2
        self.categories = catalog_pb2_grpc.CategoryServiceStub(channel)  # type: ignore[no-untyped-call]
        self.products = catalog_pb2_grpc.ProductServiceStub(channel)  # type: ignore[no-untyped-call]
        self.images = catalog_pb2_grpc.ProductImageServiceStub(channel)  # type: ignore[no-untyped-call]
