"""API Gateway proxy response builders."""

from __future__ import annotations

import json
from typing import Any

_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
}


def _envelope(status: int, body: Any, headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    return {
        "statusCode": status,
        "headers": merged,
        "body": json.dumps(body, default=str, separators=(",", ":")),
    }


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": data}
    if meta:
        body["meta"] = meta
    return _envelope(200, body)


def created(data: Any, location: str | None = None) -> dict[str, Any]:
    headers = {"Location": location} if location else None
    return _envelope(201, {"data": data}, headers)


def no_content() -> dict[str, Any]:
    return {"statusCode": 204, "headers": _DEFAULT_HEADERS, "body": ""}


def error(status: int, code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        body["details"] = details
    return _envelope(status, body)


def internal_error(request_id: str | None = None) -> dict[str, Any]:
    body = {"error": "internal_error", "message": "Something went wrong. Please retry."}
    if request_id:
        body["request_id"] = request_id
    return _envelope(500, body)
