"""DELETE /vpcs/{vpc_id} — delete AWS resources and remove the record."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from exceptions.api_exceptions import ResourceConflictError, ResourceNotFoundError
from handlers._base import extract_owner, lambda_entry, path_param
from models.vpc import VpcStatus
from services.storage_service import StorageService
from services.vpc_service import VpcService
from utils import responses
from utils.config import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


@lambda_entry("DeleteVpc")
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    settings = get_settings()
    vpc_id = path_param(event, "vpc_id")
    _ = extract_owner(event)

    storage = StorageService(settings.table_name)

    try:
        record = storage.get(vpc_id)
    except ResourceNotFoundError:
        log.info("delete_no_op_already_gone", extra={"vpc_id": vpc_id})
        return responses.no_content()

    record.status = VpcStatus.DELETING
    storage.upsert(record)

    vpc_service = VpcService()
    if record.aws_vpc_id:
        try:
            vpc_service.delete_vpc(record.aws_vpc_id)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "DependencyViolation":
                record.status = VpcStatus.ACTIVE
                storage.upsert(record)
                raise ResourceConflictError(
                    "VPC has dependent resources that must be removed first"
                ) from exc
            raise

    storage.delete(vpc_id)
    log.info("vpc_deleted_end_to_end", extra={"vpc_id": vpc_id, "aws_vpc_id": record.aws_vpc_id})
    return responses.no_content()
