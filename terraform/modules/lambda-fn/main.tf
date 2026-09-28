data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.function_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "this" {
  name   = "policy"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  filename         = var.source_zip
  source_code_hash = var.source_zip_hash
  handler          = var.handler
  runtime          = var.runtime
  architectures    = ["arm64"]
  memory_size      = var.memory_mb
  timeout          = var.timeout_seconds
  role             = aws_iam_role.this.arn

  environment {
    variables = var.environment
  }

  tracing_config {
    mode = var.xray_enabled ? "Active" : "PassThrough"
  }

  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.this]
}
