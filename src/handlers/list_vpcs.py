"""GET /vpcs — list stored VPC records, paginated."""

from __future__ import annotations

from typing import Any

from exceptions.api_exceptions import ValidationError
from handlers._base import extract_owner, lambda_entry, query_param
from services.storage_service import StorageService
from utils import responses
from utils.config import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


def _parse_limit(raw: str | None) -> int:
    if raw is None:
        return 25
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValidationError("'limit' must be an integer") from exc
    if not (1 <= limit <= 100):
        raise ValidationError("'limit' must be between 1 and 100")
    return limit


@lambda_entry("ListVpcs")
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    settings = get_settings()
    owner_id = extract_owner(event)

    limit = _parse_limit(query_param(event, "limit"))
    cursor = query_param(event, "cursor")
    scope = (query_param(event, "scope") or "mine").lower()
    if scope not in {"mine", "all"}:
        raise ValidationError("'scope' must be 'mine' or 'all'")

    storage = StorageService(settings.table_name)
    if scope == "all":
        records, next_cursor = storage.scan_all(limit=limit, cursor=cursor)
    else:
        records, next_cursor = storage.list_by_owner(owner_id, limit=limit, cursor=cursor)

    log.info("vpcs_listed", extra={"count": len(records), "scope": scope, "owner_id": owner_id})
    return responses.ok(
        [r.to_response() for r in records],
        meta={"count": len(records), "next_cursor": next_cursor, "scope": scope},
    )
