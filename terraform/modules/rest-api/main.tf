data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "archive_file" "app" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/.terraform-build/app.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"]
}

# ── IAM policy documents, one per Lambda ─────────────────────────────────
data "aws_iam_policy_document" "create_vpc" {
  statement {
    sid       = "DynamoDBWriteAndScan"
    actions   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Scan"]
    resources = [var.table_arn]
  }
  statement {
    sid = "EC2CreateAndDescribe"
    actions = [
      "ec2:CreateVpc",
      "ec2:CreateSubnet",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeAvailabilityZones",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "EC2TagOnCreate"
    actions   = ["ec2:CreateTags"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "ec2:CreateAction"
      values   = ["CreateVpc", "CreateSubnet"]
    }
  }
  statement {
    sid       = "EC2ModifyOwnedResources"
    actions   = ["ec2:ModifyVpcAttribute", "ec2:ModifySubnetAttribute"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/ManagedBy"
      values   = ["allianz-vpc-provisioner"]
    }
  }
  statement {
    sid       = "EC2RollbackOwnedResources"
    actions   = ["ec2:DeleteVpc", "ec2:DeleteSubnet"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/ManagedBy"
      values   = ["allianz-vpc-provisioner"]
    }
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*"]
  }
}

data "aws_iam_policy_document" "get_vpc" {
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:BatchGetItem"]
    resources = [var.table_arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*"]
  }
}

data "aws_iam_policy_document" "list_vpcs" {
  statement {
    actions = ["dynamodb:Query", "dynamodb:Scan", "dynamodb:GetItem"]
    resources = [
      var.table_arn,
      "${var.table_arn}/index/*",
    ]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*"]
  }
}

data "aws_iam_policy_document" "delete_vpc" {
  statement {
    sid = "DynamoDBCrud"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
    ]
    resources = [var.table_arn]
  }
  statement {
    sid       = "EC2Describe"
    actions   = ["ec2:DescribeVpcs", "ec2:DescribeSubnets"]
    resources = ["*"]
  }
  statement {
    sid       = "EC2DeleteOwnedResources"
    actions   = ["ec2:DeleteVpc", "ec2:DeleteSubnet"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/ManagedBy"
      values   = ["allianz-vpc-provisioner"]
    }
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*"]
  }
}

# ── Lambdas ──────────────────────────────────────────────────────────────
module "create_vpc" {
  source                = "../lambda-fn"
  function_name         = "${var.name_prefix}-create-vpc"
  handler               = "handlers.create_vpc.lambda_handler"
  source_zip            = data.archive_file.app.output_path
  source_zip_hash       = data.archive_file.app.output_base64sha256
  memory_mb             = var.lambda_memory_mb
  timeout_seconds       = var.lambda_timeout_seconds
  policy_json           = data.aws_iam_policy_document.create_vpc.json
  environment           = var.environment_variables
  log_retention_in_days = var.log_retention_in_days
  xray_enabled          = var.enable_xray_tracing
  tags                  = var.tags
}

module "get_vpc" {
  source                = "../lambda-fn"
  function_name         = "${var.name_prefix}-get-vpc"
  handler               = "handlers.get_vpc.lambda_handler"
  source_zip            = data.archive_file.app.output_path
  source_zip_hash       = data.archive_file.app.output_base64sha256
  memory_mb             = var.lambda_memory_mb
  timeout_seconds       = 10
  policy_json           = data.aws_iam_policy_document.get_vpc.json
  environment           = var.environment_variables
  log_retention_in_days = var.log_retention_in_days
  xray_enabled          = var.enable_xray_tracing
  tags                  = var.tags
}

module "list_vpcs" {
  source                = "../lambda-fn"
  function_name         = "${var.name_prefix}-list-vpcs"
  handler               = "handlers.list_vpcs.lambda_handler"
  source_zip            = data.archive_file.app.output_path
  source_zip_hash       = data.archive_file.app.output_base64sha256
  memory_mb             = var.lambda_memory_mb
  timeout_seconds       = 10
  policy_json           = data.aws_iam_policy_document.list_vpcs.json
  environment           = var.environment_variables
  log_retention_in_days = var.log_retention_in_days
  xray_enabled          = var.enable_xray_tracing
  tags                  = var.tags
}

module "delete_vpc" {
  source                = "../lambda-fn"
  function_name         = "${var.name_prefix}-delete-vpc"
  handler               = "handlers.delete_vpc.lambda_handler"
  source_zip            = data.archive_file.app.output_path
  source_zip_hash       = data.archive_file.app.output_base64sha256
  memory_mb             = var.lambda_memory_mb
  timeout_seconds       = var.lambda_timeout_seconds
  policy_json           = data.aws_iam_policy_document.delete_vpc.json
  environment           = var.environment_variables
  log_retention_in_days = var.log_retention_in_days
  xray_enabled          = var.enable_xray_tracing
  tags                  = var.tags
}

# ── API Gateway ──────────────────────────────────────────────────────────
resource "aws_api_gateway_rest_api" "this" {
  name = "${var.name_prefix}-api"
  lifecycle {
    create_before_destroy = true
  }
  tags = var.tags

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_authorizer" "cognito" {
  name            = "CognitoAuth"
  type            = "COGNITO_USER_POOLS"
  rest_api_id     = aws_api_gateway_rest_api.this.id
  provider_arns   = [var.user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_resource" "vpcs" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "vpcs"
}

resource "aws_api_gateway_resource" "vpc_id" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.vpcs.id
  path_part   = "{vpc_id}"
}

locals {
  routes = {
    create = { resource_id = aws_api_gateway_resource.vpcs.id, http_method = "POST", path_suffix = "vpcs", invoke_arn = module.create_vpc.invoke_arn, function_name = module.create_vpc.function_name, needs_path = false }
    list   = { resource_id = aws_api_gateway_resource.vpcs.id, http_method = "GET", path_suffix = "vpcs", invoke_arn = module.list_vpcs.invoke_arn, function_name = module.list_vpcs.function_name, needs_path = false }
    get    = { resource_id = aws_api_gateway_resource.vpc_id.id, http_method = "GET", path_suffix = "vpcs/*", invoke_arn = module.get_vpc.invoke_arn, function_name = module.get_vpc.function_name, needs_path = true }
    delete = { resource_id = aws_api_gateway_resource.vpc_id.id, http_method = "DELETE", path_suffix = "vpcs/*", invoke_arn = module.delete_vpc.invoke_arn, function_name = module.delete_vpc.function_name, needs_path = true }
  }
}

resource "aws_api_gateway_method" "this" {
  for_each      = local.routes
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = each.value.resource_id
  http_method   = each.value.http_method
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id

  request_parameters = each.value.needs_path ? {
    "method.request.path.vpc_id" = true
  } : {}
}

resource "aws_api_gateway_integration" "this" {
  for_each                = local.routes
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = each.value.resource_id
  http_method             = aws_api_gateway_method.this[each.key].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = each.value.invoke_arn
}

resource "aws_lambda_permission" "this" {
  for_each      = local.routes
  statement_id  = "AllowAPIGatewayInvoke-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/${each.value.http_method}/${each.value.path_suffix}"
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.vpcs.id,
      aws_api_gateway_resource.vpc_id.id,
      [for r in aws_api_gateway_method.this : r.id],
      [for r in aws_api_gateway_integration.this : r.id],
      aws_api_gateway_authorizer.cognito.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_api_gateway_integration.this]
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name

  xray_tracing_enabled = var.enable_xray_tracing
  tags                 = var.tags
}

resource "aws_api_gateway_method_settings" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "*/*"

  settings {
    throttling_burst_limit = var.throttle_burst_limit
    throttling_rate_limit  = var.throttle_rate_limit
    metrics_enabled        = var.metrics_enabled
  }
}

# ── SSM parameters ───────────────────────────────────────────────────────
resource "aws_ssm_parameter" "outputs" {
  for_each = {
    "api-endpoint"        = "https://${aws_api_gateway_rest_api.this.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.this.stage_name}"
    "user-pool-id"        = var.user_pool_id
    "user-pool-client-id" = var.user_pool_client_id
    "table-name"          = var.table_name
  }

  name  = "/${var.ssm_prefix}/${each.key}"
  type  = "String"
  value = each.value
  tags  = var.tags
}
