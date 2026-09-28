variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "rest_api_id" {
  type = string
}

variable "rest_api_stage" {
  type = string
}

variable "function_names" {
  type        = list(string)
  description = "Lambda function names to include in the dashboard and alarms."
}

variable "table_name" {
  type = string
}

variable "alarm_email" {
  type        = string
  default     = ""
  description = "If set, an SNS topic is created and this address is subscribed to it."
}

variable "api_5xx_threshold_percent" {
  type    = number
  default = 1
}

variable "tags" {
  type    = map(string)
  default = {}
}
