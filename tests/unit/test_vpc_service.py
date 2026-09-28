"""Unit tests for :class:`VpcService` — moto simulates real EC2 responses."""

from __future__ import annotations

import pytest

from exceptions.api_exceptions import UpstreamAwsError
from models.vpc import SubnetSpec
from services.vpc_service import VpcService


class TestCreate:
    def test_creates_vpc_and_subnets(self, ec2_client) -> None:
        service = VpcService(ec2_client=ec2_client)
        aws_vpc_id, subnets = service.create_vpc_with_subnets(
            vpc_name="unit-test",
            cidr_block="10.100.0.0/16",
            subnets=[
                SubnetSpec(
                    cidr_block="10.100.1.0/24", availability_zone="us-east-1a", is_public=True
                ),
                SubnetSpec(cidr_block="10.100.2.0/24", availability_zone="us-east-1b"),
            ],
            base_tags={"Project": "test"},
        )
        assert aws_vpc_id.startswith("vpc-")
        assert len(subnets) == 2
        assert subnets[0].is_public is True

        # Verify the VPC actually exists in the mock.
        described = ec2_client.describe_vpcs(VpcIds=[aws_vpc_id])
        assert described["Vpcs"][0]["CidrBlock"] == "10.100.0.0/16"

    def test_auto_assigns_az_when_omitted(self, ec2_client) -> None:
        service = VpcService(ec2_client=ec2_client)
        _, subnets = service.create_vpc_with_subnets(
            vpc_name="auto-az",
            cidr_block="10.101.0.0/16",
            subnets=[
                SubnetSpec(cidr_block="10.101.1.0/24"),
                SubnetSpec(cidr_block="10.101.2.0/24"),
            ],
            base_tags={},
        )
        # Every subnet should have an AZ populated even though the caller didn't specify.
        assert all(s.availability_zone for s in subnets)

    def test_rollback_on_subnet_failure(self, ec2_client, monkeypatch: pytest.MonkeyPatch) -> None:
        service = VpcService(ec2_client=ec2_client)

        original = ec2_client.create_subnet
        call_count = {"n": 0}

        def flaky_create_subnet(**kwargs):  # type: ignore[no-untyped-def]
            call_count["n"] += 1
            if call_count["n"] == 2:
                # Simulate an AWS-side failure for the second subnet.
                from botocore.exceptions import ClientError

                raise ClientError(
                    {"Error": {"Code": "InvalidSubnet.Conflict", "Message": "conflict"}},
                    "CreateSubnet",
                )
            return original(**kwargs)

        monkeypatch.setattr(ec2_client, "create_subnet", flaky_create_subnet)

        with pytest.raises(UpstreamAwsError):
            service.create_vpc_with_subnets(
                vpc_name="rollback",
                cidr_block="10.102.0.0/16",
                subnets=[
                    SubnetSpec(cidr_block="10.102.1.0/24", availability_zone="us-east-1a"),
                    SubnetSpec(cidr_block="10.102.2.0/24", availability_zone="us-east-1b"),
                ],
                base_tags={},
            )

        # After rollback, no VPCs tagged for this test should remain.
        remaining = ec2_client.describe_vpcs(
            Filters=[{"Name": "cidr", "Values": ["10.102.0.0/16"]}]
        )["Vpcs"]
        assert remaining == []


class TestDelete:
    def test_delete_removes_vpc_and_subnets(self, ec2_client) -> None:
        service = VpcService(ec2_client=ec2_client)
        aws_vpc_id, _ = service.create_vpc_with_subnets(
            vpc_name="to-delete",
            cidr_block="10.103.0.0/16",
            subnets=[SubnetSpec(cidr_block="10.103.1.0/24", availability_zone="us-east-1a")],
            base_tags={},
        )

        service.delete_vpc(aws_vpc_id)

        remaining = ec2_client.describe_vpcs(Filters=[{"Name": "vpc-id", "Values": [aws_vpc_id]}])[
            "Vpcs"
        ]
        assert remaining == []
