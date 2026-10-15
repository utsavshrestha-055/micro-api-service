"""Authentication and authorization gRPC clients."""

import grpc

from app.generated import auth_pb2, auth_pb2_grpc


class AuthClient:
    def __init__(self, channel: grpc.aio.Channel) -> None:
        self.messages = auth_pb2
        self.authentication = auth_pb2_grpc.AuthenticationServiceStub(channel)  # type: ignore[no-untyped-call]
        self.authorization = auth_pb2_grpc.AuthorizationServiceStub(channel)  # type: ignore[no-untyped-call]
