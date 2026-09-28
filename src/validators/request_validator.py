"""Validation for POST /vpcs request bodies."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

from exceptions.api_exceptions import ValidationError
from models.vpc import SubnetSpec

MAX_SUBNETS = 20
MAX_NAME_LENGTH = 64
MAX_TAGS = 25
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]*$")
_TAG_KEY_RE = re.compile(r"^[A-Za-z0-9._:/=+\-@]{1,128}$")


@dataclass(frozen=True)
class CreateVpcRequest:
    name: str
    cidr_block: str
    subnets: list[SubnetSpec]
    tags: dict[str, str]


def _require_str(obj: dict[str, Any], key: str, *, max_length: int) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"'{key}' is required and must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError(f"'{key}' must be at most {max_length} characters")
    return value


def _validate_cidr(cidr: str, *, field_name: str) -> str:
    try:
        network = ipaddress.ip_network(cidr, strict=True)
    except ValueError as exc:
        raise ValidationError(f"'{field_name}' is not a valid IPv4 CIDR: {exc}") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValidationError(f"'{field_name}' must be IPv4")
    if not (16 <= network.prefixlen <= 28):
        raise ValidationError(
            f"'{field_name}' prefix /{network.prefixlen} outside AWS range /16-/28"
        )
    return str(network)


def _validate_tags(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("'tags' must be an object of string keys and string values")
    if len(raw) > MAX_TAGS:
        raise ValidationError(f"At most {MAX_TAGS} tags are allowed")
    tags: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _TAG_KEY_RE.match(key):
            raise ValidationError(f"Invalid tag key: {key!r}")
        if not isinstance(value, str) or len(value) > 256:
            raise ValidationError(f"Tag value for {key!r} must be a string <=256 chars")
        tags[key] = value
    return tags


def _validate_subnets(raw: Any, vpc_cidr: str) -> list[SubnetSpec]:
    if not isinstance(raw, list) or not raw:
        raise ValidationError("'subnets' must be a non-empty array")
    if len(raw) > MAX_SUBNETS:
        raise ValidationError(f"At most {MAX_SUBNETS} subnets per VPC")

    vpc_network = ipaddress.ip_network(vpc_cidr, strict=True)
    seen_cidrs: set[str] = set()
    specs: list[SubnetSpec] = []

    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(f"subnets[{index}] must be an object")

        cidr = _validate_cidr(
            entry.get("cidr_block", ""), field_name=f"subnets[{index}].cidr_block"
        )
        subnet_network = ipaddress.ip_network(cidr, strict=True)

        if not (16 <= subnet_network.prefixlen <= 28):
            raise ValidationError(f"subnets[{index}].cidr_block prefix outside AWS range /16-/28")
        if not subnet_network.subnet_of(vpc_network):
            raise ValidationError(f"subnets[{index}].cidr_block is not inside the VPC CIDR")
        if cidr in seen_cidrs:
            raise ValidationError(f"subnets[{index}].cidr_block duplicates another subnet")
        seen_cidrs.add(cidr)

        name = entry.get("name")
        if name is not None and (
            not isinstance(name, str) or not _NAME_RE.match(name) or len(name) > MAX_NAME_LENGTH
        ):
            raise ValidationError(f"subnets[{index}].name is invalid")

        az = entry.get("availability_zone")
        if az is not None and (not isinstance(az, str) or not az):
            raise ValidationError(f"subnets[{index}].availability_zone must be a non-empty string")

        specs.append(
            SubnetSpec(
                cidr_block=cidr,
                availability_zone=az,
                name=name,
                is_public=bool(entry.get("is_public", False)),
            )
        )

    return specs


def find_cidr_overlap(candidate: str, existing: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Return (vpc_id, cidr) of the first record whose CIDR overlaps candidate, else None."""
    candidate_network = ipaddress.ip_network(candidate, strict=True)
    for vpc_id, cidr in existing:
        try:
            other = ipaddress.ip_network(cidr, strict=True)
        except ValueError:
            continue
        if candidate_network.overlaps(other):
            return vpc_id, cidr
    return None


def parse_create_vpc_request(payload: Any, *, allowed_cidr_prefix: str = "") -> CreateVpcRequest:
    """Validate a decoded JSON body and return a typed request."""
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")

    name = _require_str(payload, "name", max_length=MAX_NAME_LENGTH)
    if not _NAME_RE.match(name):
        raise ValidationError("'name' contains disallowed characters")

    cidr_block = _validate_cidr(payload.get("cidr_block", ""), field_name="cidr_block")
    if allowed_cidr_prefix and not cidr_block.startswith(allowed_cidr_prefix):
        raise ValidationError(
            f"'cidr_block' must start with {allowed_cidr_prefix!r} per platform policy"
        )

    subnets = _validate_subnets(payload.get("subnets"), cidr_block)
    tags = _validate_tags(payload.get("tags"))

    return CreateVpcRequest(name=name, cidr_block=cidr_block, subnets=subnets, tags=tags)
