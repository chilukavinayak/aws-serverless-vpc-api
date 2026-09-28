output "dashboard_name" {
  value = aws_cloudwatch_dashboard.this.dashboard_name
}

output "dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.this.dashboard_name}"
}

output "sns_topic_arn" {
  value = length(aws_sns_topic.alarms) > 0 ? aws_sns_topic.alarms[0].arn : null
}
