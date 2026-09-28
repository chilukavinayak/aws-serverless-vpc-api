variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "stage_name" {
  type = string
}

variable "source_dir" {
  type        = string
  description = "Path (from the module) to the Python source to package."
}

variable "table_arn" {
  type = string
}

variable "table_name" {
  type = string
}

variable "user_pool_arn" {
  type = string
}

variable "user_pool_id" {
  type = string
}

variable "user_pool_client_id" {
  type = string
}

variable "environment_variables" {
  type    = map(string)
  default = {}
}

variable "lambda_memory_mb" {
  type    = number
  default = 512
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 30
}

variable "log_retention_in_days" {
  type    = number
  default = 14
}

variable "enable_xray_tracing" {
  type    = bool
  default = false
}

variable "throttle_burst_limit" {
  type    = number
  default = 20
}

variable "throttle_rate_limit" {
  type    = number
  default = 10
}

variable "ssm_prefix" {
  type        = string
  description = "SSM Parameter Store path prefix, e.g. dev/allianz-vpc-provisioner"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "metrics_enabled" {
  type        = bool
  default     = false
  description = "API Gateway detailed CloudWatch metrics (billed as custom metrics)."
}
