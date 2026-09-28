"""
Unit tests for the CloudFormation Custom Resource handler.

We mock ``boto3`` and ``urllib.request.urlopen`` so the tests run entirely
offline. The goal is to cover every request type (Create / Update / Delete)
and the error paths that CloudFormation will actually hit in production.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from handlers import user_bootstrap


class _Context:
    aws_request_id = "test-req"
    log_stream_name = "2026/09/28/[$LATEST]abc"


def _event(request_type: str, **overrides) -> dict:
    base = {
        "RequestType": request_type,
        "RequestId": "cfn-request-id",
        "StackId": "arn:aws:cloudformation:us-east-1:0:stack/test/abc",
        "LogicalResourceId": "UserBootstrap",
        "ResponseURL": "https://cfn-signed-url.example.com/callback",
        "ResourceProperties": {
            "UserPoolId": "us-east-1_ABC",
            "Email": "demo@example.com",
            "PasswordParameterName": "/allianz-vpc-provisioner/dev/demo-user-password",
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_urlopen():
    """Replace urllib.request.urlopen with a captured mock so we can inspect the payload."""
    with patch.object(user_bootstrap.urllib.request, "urlopen") as urlopen:
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        urlopen.return_value = response
        yield urlopen


@pytest.fixture
def cognito_client():
    return MagicMock(name="cognito-idp")


@pytest.fixture
def ssm_client():
    return MagicMock(name="ssm")


@pytest.fixture
def mock_boto(cognito_client, ssm_client):
    def _factory(service_name: str, **_kwargs):
        return {"cognito-idp": cognito_client, "ssm": ssm_client}[service_name]

    with patch.object(user_bootstrap.boto3, "client", side_effect=_factory):
        yield


def _captured_body(urlopen_mock) -> dict:
    """Decode the JSON body sent back to CloudFormation."""
    call = urlopen_mock.call_args
    request = call.args[0]
    return json.loads(request.data.decode("utf-8"))


class TestCreate:
    def test_creates_user_and_signals_success(
        self, mock_urlopen, mock_boto, cognito_client, ssm_client
    ) -> None:
        user_bootstrap.lambda_handler(_event("Create"), _Context())

        cognito_client.admin_create_user.assert_called_once()
        cognito_client.admin_set_user_password.assert_called_once()
        set_kwargs = cognito_client.admin_set_user_password.call_args.kwargs
        assert set_kwargs["UserPoolId"] == "us-east-1_ABC"
        assert set_kwargs["Username"] == "demo@example.com"
        assert set_kwargs["Permanent"] is True

        ssm_client.put_parameter.assert_called_once()
        put_kwargs = ssm_client.put_parameter.call_args.kwargs
        assert put_kwargs["Name"] == "/allianz-vpc-provisioner/dev/demo-user-password"
        assert put_kwargs["Type"] == "SecureString"
        assert put_kwargs["Overwrite"] is True
        assert put_kwargs["Value"] == set_kwargs["Password"]

        body = _captured_body(mock_urlopen)
        assert body["Status"] == "SUCCESS"
        assert body["PhysicalResourceId"] == "demo@example.com"
        assert (
            body["Data"]["PasswordParameterName"]
            == "/allianz-vpc-provisioner/dev/demo-user-password"
        )

    def test_generated_password_meets_cognito_policy(self) -> None:
        password = user_bootstrap._generate_password()
        assert len(password) == 24
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in user_bootstrap._SYMBOLS for c in password)
        assert password != user_bootstrap._generate_password()

    def test_treats_existing_user_as_success(self, mock_urlopen, mock_boto, cognito_client) -> None:
        cognito_client.admin_create_user.side_effect = ClientError(
            {"Error": {"Code": "UsernameExistsException", "Message": "already"}},
            "AdminCreateUser",
        )
        user_bootstrap.lambda_handler(_event("Create"), _Context())

        cognito_client.admin_set_user_password.assert_called_once()
        assert _captured_body(mock_urlopen)["Status"] == "SUCCESS"


class TestUpdate:
    def test_update_reuses_upsert_path(self, mock_urlopen, mock_boto, cognito_client) -> None:
        user_bootstrap.lambda_handler(_event("Update"), _Context())
        assert cognito_client.admin_set_user_password.called
        assert _captured_body(mock_urlopen)["Status"] == "SUCCESS"


class TestDelete:
    def test_delete_removes_user_and_password(
        self, mock_urlopen, mock_boto, cognito_client, ssm_client
    ) -> None:
        event = _event("Delete", PhysicalResourceId="demo@example.com")
        user_bootstrap.lambda_handler(event, _Context())

        cognito_client.admin_delete_user.assert_called_once_with(
            UserPoolId="us-east-1_ABC", Username="demo@example.com"
        )
        ssm_client.delete_parameter.assert_called_once_with(
            Name="/allianz-vpc-provisioner/dev/demo-user-password"
        )
        assert _captured_body(mock_urlopen)["Status"] == "SUCCESS"

    def test_delete_swallows_missing_parameter(
        self, mock_urlopen, mock_boto, cognito_client, ssm_client
    ) -> None:
        ssm_client.delete_parameter.side_effect = ClientError(
            {"Error": {"Code": "ParameterNotFound", "Message": "gone"}}, "DeleteParameter"
        )
        event = _event("Delete", PhysicalResourceId="demo@example.com")
        user_bootstrap.lambda_handler(event, _Context())
        assert _captured_body(mock_urlopen)["Status"] == "SUCCESS"

    def test_delete_swallows_user_not_found(self, mock_urlopen, mock_boto, cognito_client) -> None:
        cognito_client.admin_delete_user.side_effect = ClientError(
            {"Error": {"Code": "UserNotFoundException", "Message": "gone"}},
            "AdminDeleteUser",
        )
        event = _event("Delete", PhysicalResourceId="demo@example.com")
        user_bootstrap.lambda_handler(event, _Context())
        assert _captured_body(mock_urlopen)["Status"] == "SUCCESS"

    def test_delete_with_no_physical_id_is_noop(
        self, mock_urlopen, mock_boto, cognito_client
    ) -> None:
        event = _event("Delete", PhysicalResourceId=None)
        user_bootstrap.lambda_handler(event, _Context())
        cognito_client.admin_delete_user.assert_not_called()
        assert _captured_body(mock_urlopen)["Status"] == "SUCCESS"


class TestErrorPaths:
    def test_missing_props_signals_failed(self, mock_urlopen, mock_boto) -> None:
        event = _event("Create")
        event["ResourceProperties"] = {}
        user_bootstrap.lambda_handler(event, _Context())
        body = _captured_body(mock_urlopen)
        assert body["Status"] == "FAILED"
        assert "Missing" in body["Reason"]

    def test_unknown_request_type_signals_failed(self, mock_urlopen, mock_boto) -> None:
        user_bootstrap.lambda_handler(_event("Frobnicate"), _Context())
        body = _captured_body(mock_urlopen)
        assert body["Status"] == "FAILED"
