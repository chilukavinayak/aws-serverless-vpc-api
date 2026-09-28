"""Unit tests for request validators — pure functions, no AWS involved."""

from __future__ import annotations

import pytest

from exceptions.api_exceptions import ValidationError
from validators.request_validator import find_cidr_overlap, parse_create_vpc_request

VALID_PAYLOAD = {
    "name": "my-vpc",
    "cidr_block": "10.0.0.0/16",
    "subnets": [
        {"cidr_block": "10.0.1.0/24", "availability_zone": "us-east-1a", "is_public": True},
        {"cidr_block": "10.0.2.0/24", "availability_zone": "us-east-1b"},
    ],
    "tags": {"CostCenter": "R&D"},
}


class TestHappyPath:
    def test_returns_typed_request(self) -> None:
        req = parse_create_vpc_request(VALID_PAYLOAD)
        assert req.name == "my-vpc"
        assert req.cidr_block == "10.0.0.0/16"
        assert len(req.subnets) == 2
        assert req.subnets[0].is_public is True
        assert req.subnets[1].is_public is False
        assert req.tags == {"CostCenter": "R&D"}

    def test_tags_default_to_empty(self) -> None:
        payload = {**VALID_PAYLOAD}
        payload.pop("tags")
        req = parse_create_vpc_request(payload)
        assert req.tags == {}

    def test_availability_zone_optional(self) -> None:
        payload = {
            **VALID_PAYLOAD,
            "subnets": [{"cidr_block": "10.0.1.0/24"}],
        }
        req = parse_create_vpc_request(payload)
        assert req.subnets[0].availability_zone is None


class TestNameRules:
    @pytest.mark.parametrize("bad_name", ["", " ", "!!!", "-starts-with-dash", "a" * 65])
    def test_invalid_names(self, bad_name: str) -> None:
        payload = {**VALID_PAYLOAD, "name": bad_name}
        with pytest.raises(ValidationError):
            parse_create_vpc_request(payload)


class TestCidrRules:
    @pytest.mark.parametrize(
        "bad_cidr",
        ["", "not-a-cidr", "10.0.0.0/8", "10.0.0.0/30", "2001:db8::/32"],
    )
    def test_invalid_vpc_cidr(self, bad_cidr: str) -> None:
        payload = {**VALID_PAYLOAD, "cidr_block": bad_cidr}
        with pytest.raises(ValidationError):
            parse_create_vpc_request(payload)

    def test_cidr_prefix_guardrail(self) -> None:
        payload = {**VALID_PAYLOAD, "cidr_block": "172.16.0.0/16"}
        with pytest.raises(ValidationError, match="policy"):
            parse_create_vpc_request(payload, allowed_cidr_prefix="10.")

    def test_subnet_outside_vpc(self) -> None:
        payload = {
            **VALID_PAYLOAD,
            "subnets": [{"cidr_block": "192.168.1.0/24"}],
        }
        with pytest.raises(ValidationError, match="not inside the VPC"):
            parse_create_vpc_request(payload)

    def test_duplicate_subnets_rejected(self) -> None:
        payload = {
            **VALID_PAYLOAD,
            "subnets": [
                {"cidr_block": "10.0.1.0/24"},
                {"cidr_block": "10.0.1.0/24"},
            ],
        }
        with pytest.raises(ValidationError, match="duplicates"):
            parse_create_vpc_request(payload)


class TestSubnetLimits:
    def test_subnets_required(self) -> None:
        payload = {**VALID_PAYLOAD, "subnets": []}
        with pytest.raises(ValidationError):
            parse_create_vpc_request(payload)

    def test_too_many_subnets(self) -> None:
        payload = {
            **VALID_PAYLOAD,
            "subnets": [{"cidr_block": f"10.0.{i}.0/24"} for i in range(21)],
        }
        with pytest.raises(ValidationError, match="At most"):
            parse_create_vpc_request(payload)


class TestTagRules:
    def test_tag_value_too_long(self) -> None:
        payload = {**VALID_PAYLOAD, "tags": {"key": "x" * 300}}
        with pytest.raises(ValidationError):
            parse_create_vpc_request(payload)

    def test_tags_must_be_object(self) -> None:
        payload = {**VALID_PAYLOAD, "tags": ["not", "an", "object"]}
        with pytest.raises(ValidationError):
            parse_create_vpc_request(payload)


class TestPayloadShape:
    def test_body_must_be_object(self) -> None:
        with pytest.raises(ValidationError, match="JSON object"):
            parse_create_vpc_request(["not", "an", "object"])


class TestCidrOverlap:
    def test_no_overlap_returns_none(self) -> None:
        existing = [("vpc-a", "10.0.0.0/16"), ("vpc-b", "10.1.0.0/16")]
        assert find_cidr_overlap("10.2.0.0/16", existing) is None

    def test_exact_match(self) -> None:
        existing = [("vpc-a", "10.0.0.0/16")]
        result = find_cidr_overlap("10.0.0.0/16", existing)
        assert result == ("vpc-a", "10.0.0.0/16")

    def test_supernet_overlaps(self) -> None:
        existing = [("vpc-a", "10.0.0.0/24")]
        result = find_cidr_overlap("10.0.0.0/16", existing)
        assert result == ("vpc-a", "10.0.0.0/24")

    def test_subnet_overlaps(self) -> None:
        existing = [("vpc-a", "10.0.0.0/16")]
        result = find_cidr_overlap("10.0.5.0/24", existing)
        assert result == ("vpc-a", "10.0.0.0/16")

    def test_empty_registry(self) -> None:
        assert find_cidr_overlap("10.0.0.0/16", []) is None

    def test_malformed_existing_cidrs_are_ignored(self) -> None:
        existing = [("vpc-bad", "not-a-cidr"), ("vpc-ok", "10.0.0.0/16")]
        assert find_cidr_overlap("10.0.0.0/16", existing) == ("vpc-ok", "10.0.0.0/16")
