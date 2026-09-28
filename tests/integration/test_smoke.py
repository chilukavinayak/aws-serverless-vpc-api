"""
End-to-end smoke test against a deployed stack.

Replaces the previous ``scripts/smoke_test.sh``. Runs entirely through boto3 +
``urllib`` — no bash, no external HTTP client dependencies.

Prerequisites
-------------
1. Stack must be deployed with a non-empty ``BootstrapUserEmail`` parameter so
   an SSM SecureString parameter holds the demo user's password.
2. AWS credentials with permissions to:
       * cloudformation:DescribeStacks
       * ssm:GetParameter (with decryption, for the demo password)
       * cognito-idp:AdminInitiateAuth    (to obtain an ID token)
3. Set ``STACK_NAME`` (the stack_name from samconfig.toml) and ``AWS_REGION``. Neither has a default.

The test is skipped unless ``-m integration`` is passed to pytest, so it never
runs during unit-test CI.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request

import boto3
import pytest

# --------------------------------------------------------------------------- guardrails
pytestmark = [pytest.mark.integration]

STACK_NAME = os.environ.get("STACK_NAME")
AWS_REGION = os.environ.get("AWS_REGION")


def _require_config() -> None:
    """Fail (not skip) with a clear message when configuration is missing. No defaults."""
    if not STACK_NAME:
        pytest.fail("STACK_NAME is not set; pass the stack_name from samconfig.toml", pytrace=False)
    if not AWS_REGION:
        pytest.fail("AWS_REGION is not set; export the region the stack lives in", pytrace=False)


# --------------------------------------------------------------------------- helpers
def _stack_outputs(stack_name: str) -> dict[str, str]:
    cfn = boto3.client("cloudformation", region_name=AWS_REGION)
    stacks = cfn.describe_stacks(StackName=stack_name)["Stacks"]
    if not stacks:
        pytest.skip(f"Stack {stack_name!r} not found — skipping integration test")
    return {o["OutputKey"]: o["OutputValue"] for o in stacks[0].get("Outputs", [])}


def _http(
    method: str, url: str, token: str | None = None, body: dict | None = None
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, context=ctx, timeout=30) as response:  # noqa: S310
            payload = response.read().decode("utf-8") or "{}"
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8") or "{}"
        return exc.code, json.loads(payload) if payload else {}


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def stack() -> dict[str, str]:
    _require_config()
    outputs = _stack_outputs(STACK_NAME)
    for required in ("ApiEndpoint", "UserPoolId", "UserPoolClientId"):
        if required not in outputs:
            pytest.fail(f"Stack output {required!r} missing — deployment incomplete?")
    if "DemoUserPasswordParameter" not in outputs or "DemoUserEmail" not in outputs:
        pytest.skip(
            "Demo user not provisioned — deploy with BootstrapUserEmail=<addr> to enable this test"
        )
    return outputs


@pytest.fixture(scope="module")
def id_token(stack: dict[str, str]) -> str:
    """Authenticate the demo user and return the Cognito ID token."""
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    password = ssm.get_parameter(Name=stack["DemoUserPasswordParameter"], WithDecryption=True)[
        "Parameter"
    ]["Value"]

    cognito = boto3.client("cognito-idp", region_name=AWS_REGION)
    response = cognito.admin_initiate_auth(
        UserPoolId=stack["UserPoolId"],
        ClientId=stack["UserPoolClientId"],
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": stack["DemoUserEmail"], "PASSWORD": password},
    )
    return response["AuthenticationResult"]["IdToken"]


# --------------------------------------------------------------------------- tests
def test_full_lifecycle(stack: dict[str, str], id_token: str) -> None:
    api = stack["ApiEndpoint"]
    body = {
        "name": "smoke-vpc",
        "cidr_block": "10.99.0.0/16",
        "subnets": [
            {"cidr_block": "10.99.1.0/24", "is_public": True},
            {"cidr_block": "10.99.2.0/24"},
        ],
        "tags": {"Purpose": "integration-smoke"},
    }

    # 1. CREATE
    status, response = _http("POST", f"{api}/vpcs", token=id_token, body=body)
    assert status == 201, response
    vpc_id = response["data"]["vpc_id"]
    aws_vpc_id = response["data"]["aws_vpc_id"]
    assert aws_vpc_id.startswith("vpc-")

    try:
        # 2. GET
        status, response = _http("GET", f"{api}/vpcs/{vpc_id}", token=id_token)
        assert status == 200, response
        assert response["data"]["vpc_id"] == vpc_id

        # 3. LIST
        status, response = _http("GET", f"{api}/vpcs", token=id_token)
        assert status == 200, response
        assert any(v["vpc_id"] == vpc_id for v in response["data"])

    finally:
        # 4. DELETE (runs even if assertions above fail — cleanup real AWS resources)
        status, response = _http("DELETE", f"{api}/vpcs/{vpc_id}", token=id_token)
        assert status in (204, 200), response


def test_unauthenticated_request_is_rejected(stack: dict[str, str]) -> None:
    status, _ = _http("GET", f"{stack['ApiEndpoint']}/vpcs")
    assert status == 401
