locals {
  send_alarms = var.alarm_email != ""

  # A 2-column grid of Lambda metric widgets (Invocations | Errors | Duration).
  lambda_widgets = flatten([
    for fn in var.function_names : [
      {
        type   = "metric"
        width  = 8
        height = 6
        properties = {
          title  = "${fn} — Invocations"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", fn]
          ]
          stat   = "Sum"
          period = 60
        }
      },
      {
        type   = "metric"
        width  = 8
        height = 6
        properties = {
          title  = "${fn} — Errors"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", fn]
          ]
          stat   = "Sum"
          period = 60
        }
      },
      {
        type   = "metric"
        width  = 8
        height = 6
        properties = {
          title  = "${fn} — Duration (p95 ms)"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", fn]
          ]
          stat   = "p95"
          period = 60
        }
      },
    ]
  ])

  dashboard_widgets = concat(
    local.lambda_widgets,
    [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway — 4XX / 5XX"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "4XXError", "ApiName", var.name_prefix, "Stage", var.rest_api_stage],
            [".", "5XXError", ".", ".", ".", "."],
          ]
          stat   = "Sum"
          period = 60
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway — Latency (p95 ms)"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiName", var.name_prefix, "Stage", var.rest_api_stage],
          ]
          stat   = "p95"
          period = 60
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB — throttled requests"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ReadThrottleEvents", "TableName", var.table_name],
            [".", "WriteThrottleEvents", ".", "."],
          ]
          stat   = "Sum"
          period = 60
        }
      },
    ],
  )
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.name_prefix}-dashboard"
  dashboard_body = jsonencode({ widgets = local.dashboard_widgets })
}

# ── SNS topic + email subscription (optional) ────────────────────────────
#tfsec:ignore:aws-sns-enable-topic-encryption CloudWatch alarms cannot publish to a topic encrypted with the AWS-managed key; a customer key costs money
resource "aws_sns_topic" "alarms" {
  count = local.send_alarms ? 1 : 0
  name  = "${var.name_prefix}-alarms"
  tags  = var.tags
}

resource "aws_sns_topic_subscription" "alarms_email" {
  count     = local.send_alarms ? 1 : 0
  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# ── Alarms ───────────────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(var.function_names)

  alarm_name          = "${each.value}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_description   = "Any Lambda error in the last 5 minutes for ${each.value}."

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = local.send_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = local.send_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name_prefix}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = var.api_5xx_threshold_percent
  treat_missing_data  = "notBreaching"
  alarm_description   = "API Gateway 5XX error rate exceeded ${var.api_5xx_threshold_percent}% over 15 minutes."

  metric_query {
    id          = "e1"
    expression  = "100 * (m5xx / MAX([m5xx + m2xx + m4xx, 1]))"
    label       = "5XX error rate %"
    return_data = true
  }

  metric_query {
    id = "m5xx"
    metric {
      metric_name = "5XXError"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions  = { ApiName = var.name_prefix, Stage = var.rest_api_stage }
    }
  }

  metric_query {
    id = "m4xx"
    metric {
      metric_name = "4XXError"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions  = { ApiName = var.name_prefix, Stage = var.rest_api_stage }
    }
  }

  metric_query {
    id = "m2xx"
    metric {
      metric_name = "Count"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions  = { ApiName = var.name_prefix, Stage = var.rest_api_stage }
    }
  }

  alarm_actions = local.send_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = local.send_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  alarm_name          = "${var.table_name}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ReadThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_description   = "DynamoDB read throttling on ${var.table_name}."

  dimensions = {
    TableName = var.table_name
  }

  alarm_actions = local.send_alarms ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = local.send_alarms ? [aws_sns_topic.alarms[0].arn] : []

  tags = var.tags
}
