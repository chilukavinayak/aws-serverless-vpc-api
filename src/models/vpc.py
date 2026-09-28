"""Data model for a VPC record."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class VpcStatus(StrEnum):
    CREATING = "CREATING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    DELETING = "DELETING"
    DELETED = "DELETED"


@dataclass(frozen=True)
class SubnetSpec:
    """User-supplied subnet definition."""

    cidr_block: str
    availability_zone: str | None = None
    name: str | None = None
    is_public: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SubnetRecord:
    """Persisted subnet metadata."""

    subnet_id: str
    cidr_block: str
    availability_zone: str
    name: str | None = None
    is_public: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VpcRecord:
    """Persisted VPC document."""

    vpc_id: str
    aws_vpc_id: str | None
    name: str
    cidr_block: str
    region: str
    owner_id: str
    status: VpcStatus
    created_at: str
    subnets: list[SubnetRecord] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    request_id: str | None = None
    error_message: str | None = None

    def to_item(self) -> dict[str, Any]:
        return {
            "vpc_id": self.vpc_id,
            "aws_vpc_id": self.aws_vpc_id,
            "name": self.name,
            "cidr_block": self.cidr_block,
            "region": self.region,
            "owner_id": self.owner_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "subnets": [s.to_dict() for s in self.subnets],
            "tags": self.tags,
            "request_id": self.request_id,
            "error_message": self.error_message,
        }

    def to_response(self) -> dict[str, Any]:
        return self.to_item()

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> VpcRecord:
        return cls(
            vpc_id=item["vpc_id"],
            aws_vpc_id=item.get("aws_vpc_id"),
            name=item["name"],
            cidr_block=item["cidr_block"],
            region=item["region"],
            owner_id=item["owner_id"],
            status=VpcStatus(item.get("status", VpcStatus.ACTIVE.value)),
            created_at=item["created_at"],
            subnets=[SubnetRecord(**s) for s in item.get("subnets", [])],
            tags=item.get("tags") or {},
            request_id=item.get("request_id"),
            error_message=item.get("error_message"),
        )


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
