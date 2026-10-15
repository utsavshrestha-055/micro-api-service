"""Stable HTTP errors for downstream gRPC failures."""

import grpc
from fastapi import HTTPException


def grpc_http_error(error: grpc.aio.AioRpcError, *, authorization: bool = False) -> HTTPException:
    code = error.code()
    if authorization:
        if code == grpc.StatusCode.UNAUTHENTICATED:
            return HTTPException(status_code=401, detail="Invalid or expired session")
        if code == grpc.StatusCode.PERMISSION_DENIED:
            return HTTPException(status_code=403, detail="Permission denied")
        if code == grpc.StatusCode.UNAVAILABLE or code == grpc.StatusCode.DEADLINE_EXCEEDED:
            return HTTPException(status_code=503, detail="Authorization service unavailable")
    mapping = {
        grpc.StatusCode.INVALID_ARGUMENT: (400, "Invalid request"),
        grpc.StatusCode.UNAUTHENTICATED: (401, "Authentication required"),
        grpc.StatusCode.PERMISSION_DENIED: (403, "Permission denied"),
        grpc.StatusCode.NOT_FOUND: (404, "Resource not found"),
        grpc.StatusCode.ALREADY_EXISTS: (409, "Resource already exists"),
        grpc.StatusCode.FAILED_PRECONDITION: (409, "Request cannot be completed"),
        grpc.StatusCode.RESOURCE_EXHAUSTED: (429, "Request limit exceeded"),
        grpc.StatusCode.UNAVAILABLE: (503, "Service unavailable"),
        grpc.StatusCode.DEADLINE_EXCEEDED: (504, "Service request timed out"),
    }
    status, detail = mapping.get(code, (502, "Service request failed"))
    return HTTPException(status_code=status, detail=detail)
