variable "project_name" {
  type = string
}

variable "environment" {
  type = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "Lowercase letters, digits and dashes, 2-16 chars."
  }
}

variable "aws_region" {
  type = string
}

variable "log_level" {
  type = string
}

variable "log_retention_in_days" {
  type = number
}

variable "lambda_memory_mb" {
  type = number
}

variable "lambda_timeout_seconds" {
  type = number
}

variable "enable_xray_tracing" {
  type = bool
}

variable "enable_point_in_time_recovery" {
  type = bool
}

variable "api_throttle_burst_limit" {
  type = number
}

variable "api_throttle_rate_limit" {
  type = number
}

variable "allowed_vpc_cidr_prefix" {
  type = string
}

variable "cognito_password_min_length" {
  type = number
}

variable "cognito_domain_prefix" {
  type = string
}

variable "oauth_callback_urls" {
  type = list(string)
}

variable "bootstrap_user_email" {
  type = string
}

variable "extra_tags" {
  type        = map(string)
  description = "Additional tags merged into the default set."
}

variable "enable_observability" {
  type        = bool
  description = "Provision the CloudWatch dashboard and alarms."
}

variable "alarm_email" {
  type        = string
  description = "If set (and observability enabled), CloudWatch alarms notify this address via SNS."
}

variable "enable_custom_metrics" {
  type        = bool
  description = "Emit EMF custom metrics and API Gateway detailed metrics (both billed beyond the free tier)."
}
