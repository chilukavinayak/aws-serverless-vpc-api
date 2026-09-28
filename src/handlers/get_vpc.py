"""GET /vpcs/{vpc_id} — fetch one VPC record."""

from __future__ import annotations

from typing import Any

from handlers._base import extract_owner, lambda_entry, path_param
from services.storage_service import StorageService
from utils import responses
from utils.config import get_settings


@lambda_entry("GetVpc")
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    settings = get_settings()
    vpc_id = path_param(event, "vpc_id")

    # Ensures the caller is authenticated; owner check would go here.
    _ = extract_owner(event)

    storage = StorageService(settings.table_name)
    record = storage.get(vpc_id)
    return responses.ok(record.to_response())
