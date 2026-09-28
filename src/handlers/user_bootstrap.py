"""Custom resource: create the Cognito demo user, store its password in SSM."""

from __future__ import annotations

import json
import secrets
import string
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import ClientError

from utils.logger import bind_context, clear_context, get_logger

log = get_logger(__name__)

_SUCCESS = "SUCCESS"
_FAILED = "FAILED"
_PASSWORD_LENGTH = 24
_SYMBOLS = "!#$%&*+-=?@^_"
_ALPHABET = string.ascii_letters + string.digits + _SYMBOLS


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    clear_context()
    bind_context(
        aws_request_id=getattr(context, "aws_request_id", None),
        stack_id=event.get("StackId"),
        logical_resource_id=event.get("LogicalResourceId"),
        request_type=event.get("RequestType"),
    )
    log.info("cfn_custom_resource_event")

    props = event.get("ResourceProperties", {}) or {}
    user_pool_id = props.get("UserPoolId")
    email = props.get("Email")
    parameter_name = props.get("PasswordParameterName")
    request_type = event.get("RequestType")

    try:
        if not (user_pool_id and email and parameter_name):
            raise ValueError(
                "Missing required ResourceProperties (UserPoolId, Email, PasswordParameterName)"
            )

        cognito = boto3.client("cognito-idp")
        ssm = boto3.client("ssm")

        if request_type in ("Create", "Update"):
            password = _generate_password()
            _upsert_user(cognito, user_pool_id, email, password)
            _store_password(ssm, parameter_name, password)
            _send(
                event,
                context,
                _SUCCESS,
                physical_id=email,
                data={"Username": email, "PasswordParameterName": parameter_name},
            )
        elif request_type == "Delete":
            _delete_user(cognito, user_pool_id, event.get("PhysicalResourceId"))
            _delete_password(ssm, parameter_name)
            _send(event, context, _SUCCESS, physical_id=event.get("PhysicalResourceId"))
        else:
            raise ValueError(f"Unsupported RequestType: {request_type!r}")

    except Exception as exc:  # noqa: BLE001 — CFN protocol requires responding on any failure
        log.exception("cfn_custom_resource_failed")
        _send(event, context, _FAILED, reason=str(exc)[:1024])


def _upsert_user(cognito: Any, user_pool_id: str, email: str, password: str) -> None:
    try:
        cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        log.info("demo_user_created", extra={"email": email})
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "UsernameExistsException":
            log.info("demo_user_exists_updating_password", extra={"email": email})
        else:
            raise

    cognito.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )
    log.info("demo_user_password_set", extra={"email": email})


def _delete_user(cognito: Any, user_pool_id: str, username: str | None) -> None:
    if not username:
        return
    try:
        cognito.admin_delete_user(UserPoolId=user_pool_id, Username=username)
        log.info("demo_user_deleted", extra={"email": username})
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("UserNotFoundException", "ResourceNotFoundException"):
            return
        raise


def _generate_password(length: int = _PASSWORD_LENGTH) -> str:
    """Random password that satisfies a Cognito policy requiring every character class."""
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in _SYMBOLS for c in candidate)
        ):
            return candidate


def _store_password(ssm: Any, name: str, password: str) -> None:
    ssm.put_parameter(
        Name=name,
        Value=password,
        Type="SecureString",
        Overwrite=True,
        Description="Cognito demo user password (managed by the UserBootstrap custom resource)",
    )
    log.info("demo_password_stored", extra={"parameter_name": name})


def _delete_password(ssm: Any, name: str) -> None:
    try:
        ssm.delete_parameter(Name=name)
        log.info("demo_password_deleted", extra={"parameter_name": name})
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ParameterNotFound":
            raise


def _send(
    event: dict[str, Any],
    context: Any,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    physical_id: str | None = None,
    reason: str | None = None,
) -> None:
    body = json.dumps(
        {
            "Status": status,
            "Reason": reason or f"See CloudWatch Logs: {getattr(context, 'log_stream_name', '')}",
            "PhysicalResourceId": physical_id
            or event.get("PhysicalResourceId")
            or getattr(context, "log_stream_name", "unknown"),
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "NoEcho": False,
            "Data": data or {},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        event["ResponseURL"],
        data=body,
        headers={"Content-Type": "", "Content-Length": str(len(body))},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 # nosec B310 — signed CFN callback URL
        log.info("cfn_response_sent", extra={"status": status, "http_status": response.status})
