variable "project_name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "github_repository" {
  type        = string
  description = "GitHub repository (<owner>/<name>) whose workflows may assume the deploy role. Set in bootstrap.auto.tfvars."
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use <owner>/<repo>."
  }
}

variable "github_owner_id" {
  type        = string
  description = "Numeric owner id (https://api.github.com/users/<owner>); GitHub's OIDC subject embeds it."
}

variable "github_repository_id" {
  type        = string
  description = "Numeric repository id (https://api.github.com/repos/<owner>/<repo>)."
}

variable "github_branch" {
  type        = string
  description = "Branch whose workflow runs may assume the deploy role."
}

variable "state_bucket_name" {
  type        = string
  description = "If empty, no S3 backend bucket is created. Bucket names are globally unique."
}
