"""POST /vpcs — create a VPC with N subnets."""

from __future__ import annotations

import uuid
from typing import Any

from exceptions.api_exceptions import ResourceConflictError
from handlers._base import extract_owner, extract_username, lambda_entry, parse_json_body
from models.vpc import VpcRecord, VpcStatus, now_iso
from services.storage_service import StorageService
from services.vpc_service import VpcService
from utils import responses
from utils.config import get_settings
from utils.logger import get_logger
from validators.request_validator import find_cidr_overlap, parse_create_vpc_request

log = get_logger(__name__)


@lambda_entry("CreateVpc")
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    settings = get_settings()

    payload = parse_json_body(event)
    request = parse_create_vpc_request(
        payload, allowed_cidr_prefix=settings.allowed_vpc_cidr_prefix
    )

    owner_id = extract_owner(event)

    storage = StorageService(settings.table_name)

    conflict = find_cidr_overlap(request.cidr_block, storage.list_active_cidrs())
    if conflict is not None:
        conflict_id, conflict_cidr = conflict
        raise ResourceConflictError(
            f"CIDR {request.cidr_block} overlaps with existing VPC {conflict_id} ({conflict_cidr})",
            details={"existing_vpc_id": conflict_id, "existing_cidr": conflict_cidr},
        )
    log.info(
        "creating_vpc",
        extra={
            "owner_id": owner_id,
            "username": extract_username(event),
            "cidr_block": request.cidr_block,
            "subnet_count": len(request.subnets),
        },
    )

    vpc_service = VpcService()

    internal_id = str(uuid.uuid4())
    base_tags = {
        **request.tags,
        "Project": settings.project_name,
        "Environment": settings.environment,
        "ManagedBy": settings.project_name,
        "InternalVpcId": internal_id,
        "OwnerId": owner_id,
    }

    aws_vpc_id, subnet_records = vpc_service.create_vpc_with_subnets(
        vpc_name=request.name,
        cidr_block=request.cidr_block,
        subnets=request.subnets,
        base_tags=base_tags,
    )

    record = VpcRecord(
        vpc_id=internal_id,
        aws_vpc_id=aws_vpc_id,
        name=request.name,
        cidr_block=request.cidr_block,
        region=settings.aws_region,
        owner_id=owner_id,
        status=VpcStatus.ACTIVE,
        created_at=now_iso(),
        subnets=subnet_records,
        tags=request.tags,
    )
    storage.put(record)

    log.info("vpc_created_successfully", extra={"vpc_id": internal_id, "aws_vpc_id": aws_vpc_id})
    return responses.created(record.to_response(), location=f"/vpcs/{internal_id}")
