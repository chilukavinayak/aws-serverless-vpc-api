variable "function_name" {
  type = string
}

variable "handler" {
  type = string
}

variable "source_zip" {
  type = string
}

variable "source_zip_hash" {
  type = string
}

variable "runtime" {
  type    = string
  default = "python3.12"
}

variable "memory_mb" {
  type    = number
  default = 512
}

variable "timeout_seconds" {
  type    = number
  default = 30
}

variable "policy_json" {
  type = string
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "log_retention_in_days" {
  type    = number
  default = 14
}

variable "xray_enabled" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
