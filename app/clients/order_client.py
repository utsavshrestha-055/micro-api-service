"""Customer-scoped order gRPC client."""

import grpc

from app.generated import orders_pb2, orders_pb2_grpc


class OrderClient:
    def __init__(self, channel: grpc.aio.Channel) -> None:
        self.messages = orders_pb2
        self.orders = orders_pb2_grpc.OrderServiceStub(channel)  # type: ignore[no-untyped-call]
