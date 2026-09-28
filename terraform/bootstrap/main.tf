data "aws_caller_identity" "current" {}
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}
data "aws_iam_policy_document" "assume_from_github" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/${var.github_branch}",
        "repo:${local.gh_owner}@${var.github_owner_id}/${local.gh_repo}@${var.github_repository_id}:ref:refs/heads/${var.github_branch}",
      ]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.project_name}-deploy"
  assume_role_policy   = data.aws_iam_policy_document.assume_from_github.json
  max_session_duration = 3600
}

data "aws_region" "current" {}

locals {
  gh_owner   = split("/", var.github_repository)[0]
  gh_repo    = split("/", var.github_repository)[1]
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  p          = var.project_name
}
data "aws_iam_policy_document" "deploy" {
  statement {
    sid     = "CloudFormationProjectStacks"
    actions = ["cloudformation:*"]
    resources = [
      "arn:aws:cloudformation:${local.region}:${local.account_id}:stack/${local.p}-*/*",
      "arn:aws:cloudformation:${local.region}:${local.account_id}:stack/aws-sam-cli-managed-default/*",
    ]
  }

  statement {
    sid       = "CloudFormationSamTransform"
    actions   = ["cloudformation:CreateChangeSet"]
    resources = ["arn:aws:cloudformation:${local.region}:aws:transform/Serverless-2016-10-31"]
  }

  statement {
    sid = "ReadOnlyDiscovery"
    actions = [
      "cloudformation:ValidateTemplate",
      "cloudformation:ListStacks",
      "cloudformation:DescribeStacks",
      "logs:DescribeLogGroups",
      "ssm:DescribeParameters",
      "cloudwatch:DescribeAlarms",
    ]
    resources = ["*"]
  }

  statement {
    sid     = "SamArtifactBucket"
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::aws-sam-cli-managed-default-*",
      "arn:aws:s3:::aws-sam-cli-managed-default-*/*",
    ]
  }

  statement {
    sid       = "LambdaProjectFunctions"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:${local.region}:${local.account_id}:function:${local.p}-*"]
  }

  statement {
    sid = "IamProjectRoles"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:PassRole",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.p}-*"]
  }

  statement {
    sid       = "DynamoProjectTables"
    actions   = ["dynamodb:*"]
    resources = ["arn:aws:dynamodb:${local.region}:${local.account_id}:table/${local.p}-*"]
  }

  statement {
    sid     = "ApiGateway"
    actions = ["apigateway:*"]
    resources = [
      "arn:aws:apigateway:${local.region}::/restapis",
      "arn:aws:apigateway:${local.region}::/restapis/*",
      "arn:aws:apigateway:${local.region}::/tags/*",
    ]
  }

  statement {
    sid = "Cognito"
    actions = [
      "cognito-idp:CreateUserPool",
      "cognito-idp:DeleteUserPool",
      "cognito-idp:UpdateUserPool",
      "cognito-idp:DescribeUserPool",
      "cognito-idp:CreateUserPoolClient",
      "cognito-idp:DeleteUserPoolClient",
      "cognito-idp:UpdateUserPoolClient",
      "cognito-idp:DescribeUserPoolClient",
      "cognito-idp:CreateUserPoolDomain",
      "cognito-idp:DeleteUserPoolDomain",
      "cognito-idp:UpdateUserPoolDomain",
      "cognito-idp:DescribeUserPoolDomain",
      "cognito-idp:SetUserPoolMfaConfig",
      "cognito-idp:GetUserPoolMfaConfig",
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminSetUserPassword",
      "cognito-idp:AdminInitiateAuth",
      "cognito-idp:TagResource",
      "cognito-idp:UntagResource",
      "cognito-idp:ListTagsForResource",
    ]
    resources = ["*"]
  }

  statement {
    sid = "LogsProjectGroups"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
      "logs:TagLogGroup",
      "logs:UntagLogGroup",
      "logs:ListTagsForResource",
      "logs:ListTagsLogGroup",
    ]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.p}-*"]
  }

  statement {
    sid = "SsmProjectParameters"
    actions = [
      "ssm:PutParameter",
      "ssm:DeleteParameter",
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:AddTagsToResource",
      "ssm:RemoveTagsFromResource",
      "ssm:ListTagsForResource",
    ]
    resources = ["arn:aws:ssm:${local.region}:${local.account_id}:parameter/${local.p}/*"]
  }

  statement {
    sid = "ObservabilityOptional"
    actions = [
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:DeleteAlarms",
      "cloudwatch:PutDashboard",
      "cloudwatch:DeleteDashboards",
      "cloudwatch:GetDashboard",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
      "cloudwatch:ListTagsForResource",
    ]
    resources = [
      "arn:aws:cloudwatch:${local.region}:${local.account_id}:alarm:${local.p}-*",
      "arn:aws:cloudwatch::${local.account_id}:dashboard/${local.p}-*",
    ]
  }

  statement {
    sid       = "SnsOptional"
    actions   = ["sns:*"]
    resources = ["arn:aws:sns:${local.region}:${local.account_id}:${local.p}-*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
resource "aws_s3_bucket" "state" {
  count  = var.state_bucket_name == "" ? 0 : 1
  bucket = var.state_bucket_name
}

resource "aws_s3_bucket_versioning" "state" {
  count  = var.state_bucket_name == "" ? 0 : 1
  bucket = aws_s3_bucket.state[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  count  = var.state_bucket_name == "" ? 0 : 1
  bucket = aws_s3_bucket.state[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  count                   = var.state_bucket_name == "" ? 0 : 1
  bucket                  = aws_s3_bucket.state[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "state_lock" {
  count        = var.state_bucket_name == "" ? 0 : 1
  name         = "${var.project_name}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}
