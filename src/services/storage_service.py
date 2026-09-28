"""DynamoDB CRUD for VpcRecord."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import ClientError

from exceptions.api_exceptions import ResourceNotFoundError, UpstreamAwsError
from models.vpc import VpcRecord
from utils.logger import get_logger

log = get_logger(__name__)

OWNER_INDEX = "OwnerIndex"


class StorageService:
    def __init__(self, table_name: str, dynamodb_resource: Any | None = None) -> None:
        self._table_name = table_name
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    def put(self, record: VpcRecord) -> None:
        try:
            self._table.put_item(
                Item=record.to_item(),
                ConditionExpression="attribute_not_exists(vpc_id)",
            )
            log.info("dynamodb_put", extra={"vpc_id": record.vpc_id})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                raise UpstreamAwsError(f"vpc_id {record.vpc_id!r} already exists") from exc
            log.exception("dynamodb_put_failed", extra={"vpc_id": record.vpc_id})
            raise UpstreamAwsError("Failed to persist VPC record") from exc

    def upsert(self, record: VpcRecord) -> None:
        try:
            self._table.put_item(Item=record.to_item())
        except ClientError as exc:
            log.exception("dynamodb_upsert_failed", extra={"vpc_id": record.vpc_id})
            raise UpstreamAwsError("Failed to persist VPC record") from exc

    def get(self, vpc_id: str) -> VpcRecord:
        try:
            response = self._table.get_item(Key={"vpc_id": vpc_id})
        except ClientError as exc:
            log.exception("dynamodb_get_failed", extra={"vpc_id": vpc_id})
            raise UpstreamAwsError("Failed to read VPC record") from exc
        item = response.get("Item")
        if not item:
            raise ResourceNotFoundError(f"No VPC with id {vpc_id!r}")
        return VpcRecord.from_item(item)

    def delete(self, vpc_id: str) -> None:
        try:
            self._table.delete_item(Key={"vpc_id": vpc_id})
            log.info("dynamodb_delete", extra={"vpc_id": vpc_id})
        except ClientError as exc:
            log.exception("dynamodb_delete_failed", extra={"vpc_id": vpc_id})
            raise UpstreamAwsError("Failed to delete VPC record") from exc

    def list_by_owner(
        self,
        owner_id: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> tuple[list[VpcRecord], str | None]:
        kwargs: dict[str, Any] = {
            "IndexName": OWNER_INDEX,
            "KeyConditionExpression": "owner_id = :o",
            "ExpressionAttributeValues": {":o": owner_id},
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if cursor:
            kwargs["ExclusiveStartKey"] = {
                "vpc_id": cursor,
                "owner_id": owner_id,
                "created_at": cursor,
            }
        try:
            response = self._table.query(**kwargs)
        except ClientError as exc:
            log.exception("dynamodb_list_by_owner_failed", extra={"owner_id": owner_id})
            raise UpstreamAwsError("Failed to list VPC records") from exc

        items = [VpcRecord.from_item(item) for item in response.get("Items", [])]
        last = response.get("LastEvaluatedKey")
        return items, (last.get("vpc_id") if last else None)

    def list_active_cidrs(self) -> list[tuple[str, str]]:
        """Return [(vpc_id, cidr_block), ...] for every record not in DELETED status."""
        try:
            response = self._table.scan(
                ProjectionExpression="vpc_id, cidr_block, #s",
                ExpressionAttributeNames={"#s": "status"},
            )
        except ClientError as exc:
            log.exception("dynamodb_list_active_cidrs_failed")
            raise UpstreamAwsError("Failed to list VPC CIDRs") from exc

        active: list[tuple[str, str]] = []
        for item in response.get("Items", []):
            if item.get("status") == "DELETED":
                continue
            cidr = item.get("cidr_block")
            vpc_id = item.get("vpc_id")
            if cidr and vpc_id:
                active.append((vpc_id, cidr))
        return active

    def scan_all(
        self,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> tuple[list[VpcRecord], str | None]:
        kwargs: dict[str, Any] = {"Limit": limit}
        if cursor:
            kwargs["ExclusiveStartKey"] = {"vpc_id": cursor}
        try:
            response = self._table.scan(**kwargs)
        except ClientError as exc:
            log.exception("dynamodb_scan_failed")
            raise UpstreamAwsError("Failed to list VPC records") from exc

        items = [VpcRecord.from_item(item) for item in response.get("Items", [])]
        last = response.get("LastEvaluatedKey")
        return items, (last.get("vpc_id") if last else None)
