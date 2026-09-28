"""
Handler-level tests — end-to-end through the Lambda entrypoints.

We do NOT mock the service layer; we let the real code run against the moto
stand-ins for EC2 + DynamoDB. This gives us high confidence that the wiring
between handler → service → AWS is correct.
"""

from __future__ import annotations

import json

from handlers import create_vpc, delete_vpc, get_vpc, list_vpcs


# -----------------------------------------------------------------------------
# Full happy-path pipeline
# -----------------------------------------------------------------------------
class TestCreateReadList:
    def test_create_then_get_then_list(
        self,
        dynamodb_table,
        ec2_client,
        api_event,
        lambda_context,
    ) -> None:
        # -------- 1. CREATE
        body = json.dumps(
            {
                "name": "handler-test",
                "cidr_block": "10.50.0.0/16",
                "subnets": [
                    {
                        "cidr_block": "10.50.1.0/24",
                        "availability_zone": "us-east-1a",
                        "is_public": True,
                    },
                    {"cidr_block": "10.50.2.0/24", "availability_zone": "us-east-1b"},
                ],
                "tags": {"Team": "platform"},
            }
        )
        event = api_event(method="POST", path="/vpcs", body=body)
        response = create_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 201
        created = json.loads(response["body"])["data"]
        vpc_id = created["vpc_id"]
        assert created["aws_vpc_id"].startswith("vpc-")
        assert len(created["subnets"]) == 2
        assert created["status"] == "ACTIVE"

        # -------- 2. GET
        event = api_event(method="GET", path=f"/vpcs/{vpc_id}", path_parameters={"vpc_id": vpc_id})
        response = get_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 200
        fetched = json.loads(response["body"])["data"]
        assert fetched["vpc_id"] == vpc_id

        # -------- 3. LIST (mine)
        event = api_event(method="GET", path="/vpcs")
        response = list_vpcs.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 200
        listing = json.loads(response["body"])
        assert listing["meta"]["count"] == 1
        assert listing["data"][0]["vpc_id"] == vpc_id

        # -------- 4. DELETE
        event = api_event(
            method="DELETE", path=f"/vpcs/{vpc_id}", path_parameters={"vpc_id": vpc_id}
        )
        response = delete_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 204

        # -------- 5. GET after delete
        event = api_event(method="GET", path=f"/vpcs/{vpc_id}", path_parameters={"vpc_id": vpc_id})
        response = get_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 404


# -----------------------------------------------------------------------------
# Error paths
# -----------------------------------------------------------------------------
class TestCreateErrors:
    def test_missing_body(self, dynamodb_table, ec2_client, api_event, lambda_context) -> None:
        event = api_event(method="POST", path="/vpcs", body=None)
        response = create_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == "validation_error"

    def test_invalid_cidr(self, dynamodb_table, ec2_client, api_event, lambda_context) -> None:
        body = json.dumps({"name": "bad", "cidr_block": "10.0.0.0/8", "subnets": []})
        event = api_event(method="POST", path="/vpcs", body=body)
        response = create_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 400

    def test_cidr_policy_violation(
        self, dynamodb_table, ec2_client, api_event, lambda_context
    ) -> None:
        body = json.dumps(
            {
                "name": "outside-policy",
                "cidr_block": "192.168.0.0/16",
                "subnets": [{"cidr_block": "192.168.1.0/24"}],
            }
        )
        event = api_event(method="POST", path="/vpcs", body=body)
        response = create_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 400
        assert "policy" in json.loads(response["body"])["message"].lower()


class TestCidrOverlapRejection:
    def test_second_create_with_overlapping_cidr_returns_409(
        self, dynamodb_table, ec2_client, api_event, lambda_context
    ) -> None:
        # First create succeeds
        body = json.dumps(
            {
                "name": "first",
                "cidr_block": "10.70.0.0/16",
                "subnets": [{"cidr_block": "10.70.1.0/24"}],
            }
        )
        r1 = create_vpc.lambda_handler(
            api_event(method="POST", path="/vpcs", body=body), lambda_context
        )
        assert r1["statusCode"] == 201

        # Second create with overlapping supernet must be rejected
        body = json.dumps(
            {
                "name": "second",
                "cidr_block": "10.70.0.0/20",
                "subnets": [{"cidr_block": "10.70.0.0/24"}],
            }
        )
        r2 = create_vpc.lambda_handler(
            api_event(method="POST", path="/vpcs", body=body), lambda_context
        )
        assert r2["statusCode"] == 409
        payload = json.loads(r2["body"])
        assert payload["error"] == "conflict"
        assert "existing_vpc_id" in payload["details"]


class TestGetNotFound:
    def test_returns_404(self, dynamodb_table, api_event, lambda_context) -> None:
        event = api_event(
            method="GET",
            path="/vpcs/ghost",
            path_parameters={"vpc_id": "ghost"},
        )
        response = get_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 404


class TestDeleteIdempotent:
    def test_delete_missing_returns_204(
        self, dynamodb_table, ec2_client, api_event, lambda_context
    ) -> None:
        event = api_event(
            method="DELETE",
            path="/vpcs/ghost",
            path_parameters={"vpc_id": "ghost"},
        )
        response = delete_vpc.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 204


class TestListingPagination:
    def test_scope_all_lists_across_users(
        self, dynamodb_table, ec2_client, api_event, lambda_context
    ) -> None:
        # Create as user A
        body = json.dumps(
            {
                "name": "u1-vpc",
                "cidr_block": "10.60.0.0/16",
                "subnets": [{"cidr_block": "10.60.1.0/24"}],
            }
        )
        create_vpc.lambda_handler(
            api_event(method="POST", path="/vpcs", body=body, owner_id="user-a"),
            lambda_context,
        )
        # Create as user B
        body = json.dumps(
            {
                "name": "u2-vpc",
                "cidr_block": "10.61.0.0/16",
                "subnets": [{"cidr_block": "10.61.1.0/24"}],
            }
        )
        create_vpc.lambda_handler(
            api_event(method="POST", path="/vpcs", body=body, owner_id="user-b"),
            lambda_context,
        )

        # User A sees only their own by default…
        event = api_event(method="GET", path="/vpcs", owner_id="user-a")
        response = list_vpcs.lambda_handler(event, lambda_context)
        assert json.loads(response["body"])["meta"]["count"] == 1

        # …but scope=all sees everything.
        event = api_event(
            method="GET",
            path="/vpcs",
            owner_id="user-a",
            query_parameters={"scope": "all"},
        )
        response = list_vpcs.lambda_handler(event, lambda_context)
        assert json.loads(response["body"])["meta"]["count"] == 2

    def test_invalid_limit_returns_400(self, dynamodb_table, api_event, lambda_context) -> None:
        event = api_event(method="GET", path="/vpcs", query_parameters={"limit": "9999"})
        response = list_vpcs.lambda_handler(event, lambda_context)
        assert response["statusCode"] == 400
