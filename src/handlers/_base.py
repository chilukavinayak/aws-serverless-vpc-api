"""Shared helpers for API Gateway proxy Lambda handlers."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any

from exceptions.api_exceptions import ApiError, ValidationError
from utils import responses
from utils.logger import bind_context, clear_context, get_logger
from utils.metrics import Metrics

log = get_logger(__name__)


def lambda_entry(operation: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a handler with logging context, metrics, and error mapping."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(event: dict[str, Any], context: Any) -> dict[str, Any]:
            clear_context()
            aws_request_id = getattr(context, "aws_request_id", None)
            api_request_id = (event.get("requestContext") or {}).get("requestId")
            bind_context(
                aws_request_id=aws_request_id,
                correlation_id=api_request_id or aws_request_id,
                operation=operation,
            )
            log.info(
                "handler_invoked",
                extra={"path": event.get("path"), "method": event.get("httpMethod")},
            )

            with Metrics(operation) as m:
                try:
                    result = fn(event, context)
                    m.count("Success", 1)
                    return result
                except ApiError as exc:
                    m.count(exc.error_code, 1)
                    log.warning(
                        "handler_api_error",
                        extra={"error_code": exc.error_code, "error_message": exc.message},
                    )
                    return responses.error(
                        exc.status_code, exc.error_code, exc.message, exc.details
                    )
                except Exception:
                    m.count("UnhandledException", 1)
                    log.exception("handler_unhandled_exception")
                    return responses.internal_error(aws_request_id)

        return wrapper

    return decorator


def extract_owner(event: dict[str, Any]) -> str:
    """Return the Cognito `sub` claim of the authenticated caller."""
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
    sub = claims.get("sub")
    if not sub:
        raise ApiError("Authenticated user is missing 'sub' claim")
    return sub


def extract_username(event: dict[str, Any]) -> str | None:
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
    return claims.get("email") or claims.get("cognito:username")


def parse_json_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if body is None or body == "":
        raise ValidationError("Request body is required")
    if event.get("isBase64Encoded"):
        import base64

        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception as exc:
            raise ValidationError("Request body is not valid base64") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Request body is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    return payload


def path_param(event: dict[str, Any], name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name)
    if not value:
        raise ValidationError(f"Missing path parameter: {name}")
    return value


def query_param(event: dict[str, Any], name: str, default: str | None = None) -> str | None:
    return (event.get("queryStringParameters") or {}).get(name, default)
