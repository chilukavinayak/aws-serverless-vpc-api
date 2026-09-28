"""Unit tests for :class:`StorageService` using moto-mocked DynamoDB."""

from __future__ import annotations

import pytest

from exceptions.api_exceptions import ResourceNotFoundError, UpstreamAwsError
from models.vpc import VpcRecord, VpcStatus, now_iso
from services.storage_service import StorageService


def _record(vpc_id: str = "vpc-1", owner: str = "user-a") -> VpcRecord:
    return VpcRecord(
        vpc_id=vpc_id,
        aws_vpc_id="vpc-aws-abc",
        name="unit-test",
        cidr_block="10.0.0.0/16",
        region="us-east-1",
        owner_id=owner,
        status=VpcStatus.ACTIVE,
        created_at=now_iso(),
    )


class TestPutGet:
    def test_put_then_get(self, dynamodb_table: str) -> None:
        svc = StorageService(dynamodb_table)
        record = _record()
        svc.put(record)
        result = svc.get("vpc-1")
        assert result.vpc_id == "vpc-1"
        assert result.status is VpcStatus.ACTIVE

    def test_get_missing_raises(self, dynamodb_table: str) -> None:
        svc = StorageService(dynamodb_table)
        with pytest.raises(ResourceNotFoundError):
            svc.get("does-not-exist")

    def test_put_conflict(self, dynamodb_table: str) -> None:
        svc = StorageService(dynamodb_table)
        svc.put(_record())
        with pytest.raises(UpstreamAwsError, match="already exists"):
            svc.put(_record())


class TestDelete:
    def test_delete_removes_record(self, dynamodb_table: str) -> None:
        svc = StorageService(dynamodb_table)
        svc.put(_record())
        svc.delete("vpc-1")
        with pytest.raises(ResourceNotFoundError):
            svc.get("vpc-1")

    def test_delete_is_idempotent(self, dynamodb_table: str) -> None:
        # Deleting a missing item should not raise.
        StorageService(dynamodb_table).delete("never-existed")


class TestListing:
    def test_list_by_owner(self, dynamodb_table: str) -> None:
        svc = StorageService(dynamodb_table)
        svc.put(_record("vpc-a", "user-a"))
        svc.put(_record("vpc-b", "user-a"))
        svc.put(_record("vpc-c", "user-b"))

        items, cursor = svc.list_by_owner("user-a")
        assert {r.vpc_id for r in items} == {"vpc-a", "vpc-b"}
        assert cursor is None

    def test_scan_all(self, dynamodb_table: str) -> None:
        svc = StorageService(dynamodb_table)
        svc.put(_record("vpc-a", "user-a"))
        svc.put(_record("vpc-b", "user-b"))
        items, _ = svc.scan_all()
        assert len(items) == 2
