variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "password_min_length" {
  type    = number
  default = 12
}

variable "enable_mfa" {
  type    = bool
  default = false
}

variable "oauth_callback_urls" {
  type    = list(string)
  default = ["https://oauth.pstmn.io/v1/callback"]
}

variable "hosted_ui_domain_prefix" {
  type    = string
  default = ""
}

variable "bootstrap_user_email" {
  type    = string
  default = ""
}

variable "ssm_prefix" {
  type        = string
  description = "SSM path prefix, e.g. allianz-vpc-provisioner/dev"
}

variable "tags" {
  type    = map(string)
  default = {}
}
