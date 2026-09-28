output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}

output "deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository secret in GitHub."
  value       = aws_iam_role.deploy.arn
}

output "state_bucket" {
  value = var.state_bucket_name == "" ? null : aws_s3_bucket.state[0].bucket
}

output "state_lock_table" {
  value = var.state_bucket_name == "" ? null : aws_dynamodb_table.state_lock[0].name
}
