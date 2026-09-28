"""EC2 VPC and subnet lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import boto3
from botocore.exceptions import ClientError

from exceptions.api_exceptions import UpstreamAwsError, ValidationError
from models.vpc import SubnetRecord, SubnetSpec
from utils.logger import get_logger

log = get_logger(__name__)


class VpcService:
    def __init__(self, ec2_client: Any | None = None) -> None:
        self._ec2 = ec2_client or boto3.client("ec2")

    def create_vpc_with_subnets(
        self,
        *,
        vpc_name: str,
        cidr_block: str,
        subnets: list[SubnetSpec],
        base_tags: dict[str, str],
    ) -> tuple[str, list[SubnetRecord]]:
        """Create a VPC and all its subnets. Roll back on any failure."""
        aws_vpc_id = self._create_vpc(cidr_block, vpc_name, base_tags)
        created_subnets: list[SubnetRecord] = []
        try:
            az_iterator = self._az_iterator()
            for index, spec in enumerate(subnets):
                az = spec.availability_zone or next(az_iterator)
                subnet_name = spec.name or f"{vpc_name}-subnet-{index + 1}"
                subnet_id = self._create_subnet(
                    aws_vpc_id=aws_vpc_id,
                    cidr_block=spec.cidr_block,
                    availability_zone=az,
                    name=subnet_name,
                    is_public=spec.is_public,
                    base_tags=base_tags,
                )
                created_subnets.append(
                    SubnetRecord(
                        subnet_id=subnet_id,
                        cidr_block=spec.cidr_block,
                        availability_zone=az,
                        name=subnet_name,
                        is_public=spec.is_public,
                    )
                )
            self._safe_enable_dns(aws_vpc_id)
            return aws_vpc_id, created_subnets
        except Exception:
            log.exception(
                "vpc_creation_failed_rolling_back",
                extra={
                    "aws_vpc_id": aws_vpc_id,
                    "created_subnets": [s.subnet_id for s in created_subnets],
                },
            )
            self._best_effort_rollback(aws_vpc_id, [s.subnet_id for s in created_subnets])
            raise

    def delete_vpc(self, aws_vpc_id: str) -> None:
        """Delete every subnet in the VPC, then the VPC itself."""
        subnet_ids = self._describe_subnet_ids(aws_vpc_id)
        for subnet_id in subnet_ids:
            self._call(self._ec2.delete_subnet, SubnetId=subnet_id)
            log.info("subnet_deleted", extra={"subnet_id": subnet_id})
        self._call(self._ec2.delete_vpc, VpcId=aws_vpc_id)
        log.info("vpc_deleted", extra={"aws_vpc_id": aws_vpc_id})

    def _create_vpc(self, cidr_block: str, name: str, base_tags: dict[str, str]) -> str:
        tag_spec = self._tag_specification("vpc", {**base_tags, "Name": name})
        response = self._call(
            self._ec2.create_vpc,
            CidrBlock=cidr_block,
            TagSpecifications=[tag_spec],
            AmazonProvidedIpv6CidrBlock=False,
        )
        aws_vpc_id = response["Vpc"]["VpcId"]
        log.info("vpc_created", extra={"aws_vpc_id": aws_vpc_id, "cidr_block": cidr_block})

        try:
            self._ec2.get_waiter("vpc_available").wait(
                VpcIds=[aws_vpc_id],
                WaiterConfig={"Delay": 2, "MaxAttempts": 15},
            )
        except ClientError as exc:
            raise UpstreamAwsError(f"VPC {aws_vpc_id} did not become available") from exc

        return aws_vpc_id

    def _create_subnet(
        self,
        *,
        aws_vpc_id: str,
        cidr_block: str,
        availability_zone: str,
        name: str,
        is_public: bool,
        base_tags: dict[str, str],
    ) -> str:
        tags = {**base_tags, "Name": name, "Tier": "public" if is_public else "private"}
        response = self._call(
            self._ec2.create_subnet,
            VpcId=aws_vpc_id,
            CidrBlock=cidr_block,
            AvailabilityZone=availability_zone,
            TagSpecifications=[self._tag_specification("subnet", tags)],
        )
        subnet_id = response["Subnet"]["SubnetId"]
        log.info(
            "subnet_created",
            extra={
                "subnet_id": subnet_id,
                "aws_vpc_id": aws_vpc_id,
                "cidr_block": cidr_block,
                "availability_zone": availability_zone,
            },
        )

        if is_public:
            try:
                self._ec2.modify_subnet_attribute(
                    SubnetId=subnet_id,
                    MapPublicIpOnLaunch={"Value": True},
                )
            except ClientError:
                log.warning("failed_to_enable_public_ip_on_launch", extra={"subnet_id": subnet_id})

        return subnet_id

    def _safe_enable_dns(self, aws_vpc_id: str) -> None:
        try:
            self._ec2.modify_vpc_attribute(VpcId=aws_vpc_id, EnableDnsSupport={"Value": True})
            self._ec2.modify_vpc_attribute(VpcId=aws_vpc_id, EnableDnsHostnames={"Value": True})
        except ClientError:
            log.warning("failed_to_enable_vpc_dns", extra={"aws_vpc_id": aws_vpc_id})

    def _az_iterator(self) -> Iterator[str]:
        try:
            response = self._ec2.describe_availability_zones(
                Filters=[{"Name": "state", "Values": ["available"]}]
            )
        except ClientError as exc:
            raise UpstreamAwsError("Could not list availability zones") from exc

        zones = [z["ZoneName"] for z in response.get("AvailabilityZones", [])]
        if not zones:
            raise ValidationError("No availability zones available in this region")

        index = 0
        while True:
            yield zones[index % len(zones)]
            index += 1

    def _describe_subnet_ids(self, aws_vpc_id: str) -> list[str]:
        response = self._call(
            self._ec2.describe_subnets,
            Filters=[{"Name": "vpc-id", "Values": [aws_vpc_id]}],
        )
        return [s["SubnetId"] for s in response.get("Subnets", [])]

    def _best_effort_rollback(self, aws_vpc_id: str, subnet_ids: list[str]) -> None:
        for subnet_id in subnet_ids:
            try:
                self._ec2.delete_subnet(SubnetId=subnet_id)
                log.info("rollback_subnet_deleted", extra={"subnet_id": subnet_id})
            except ClientError:
                log.exception("rollback_subnet_delete_failed", extra={"subnet_id": subnet_id})
        try:
            self._ec2.delete_vpc(VpcId=aws_vpc_id)
            log.info("rollback_vpc_deleted", extra={"aws_vpc_id": aws_vpc_id})
        except ClientError:
            log.exception("rollback_vpc_delete_failed", extra={"aws_vpc_id": aws_vpc_id})

    @staticmethod
    def _tag_specification(resource_type: str, tags: dict[str, str]) -> dict[str, Any]:
        return {
            "ResourceType": resource_type,
            "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
        }

    @staticmethod
    def _call(fn: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            msg = exc.response.get("Error", {}).get("Message", str(exc))
            log.error(
                "aws_client_error",
                extra={"aws_code": code, "aws_message": msg, "operation": fn.__name__},
            )
            raise UpstreamAwsError(
                f"AWS {fn.__name__} failed: {code}", details={"aws_code": code}
            ) from exc
