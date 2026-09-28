"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TABLE_NAME", "test-vpcs")
    monkeypatch.setenv("PROJECT_NAME", "test-allianz-vpc-provisioner")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("ALLOWED_VPC_CIDR_PREFIX", "10.")
    monkeypatch.setenv("CUSTOM_METRICS_ENABLED", "false")

    from utils.config import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def aws() -> Iterator[None]:
    with mock_aws():
        yield


@pytest.fixture
def dynamodb_table(aws: None) -> Iterator[str]:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    resource.create_table(
        TableName="test-vpcs",
        AttributeDefinitions=[
            {"AttributeName": "vpc_id", "AttributeType": "S"},
            {"AttributeName": "owner_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "vpc_id", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "OwnerIndex",
                "KeySchema": [
                    {"AttributeName": "owner_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    yield "test-vpcs"


@pytest.fixture
def ec2_client(aws: None):
    return boto3.client("ec2", region_name="us-east-1")


@pytest.fixture
def api_event() -> callable:
    def _make(
        method: str = "GET",
        path: str = "/vpcs",
        body: str | None = None,
        path_parameters: dict[str, str] | None = None,
        query_parameters: dict[str, str] | None = None,
        owner_id: str = "test-user-sub",
        email: str = "tester@example.com",
    ) -> dict:
        return {
            "httpMethod": method,
            "path": path,
            "body": body,
            "isBase64Encoded": False,
            "pathParameters": path_parameters,
            "queryStringParameters": query_parameters,
            "headers": {"Content-Type": "application/json"},
            "requestContext": {
                "requestId": "test-request-id",
                "authorizer": {
                    "claims": {
                        "sub": owner_id,
                        "email": email,
                        "cognito:username": email,
                    }
                },
            },
        }

    return _make


class _FakeLambdaContext:
    aws_request_id = "test-aws-request-id"
    function_name = "test-fn"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:000000000000:function:test-fn"
    log_stream_name = "test-stream"


@pytest.fixture
def lambda_context() -> _FakeLambdaContext:
    return _FakeLambdaContext()
