output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.this.arn
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.this.id
}

output "hosted_ui_domain" {
  value = var.hosted_ui_domain_prefix == "" ? null : aws_cognito_user_pool_domain.this[0].domain
}

output "hosted_ui_sign_in_url" {
  value = var.hosted_ui_domain_prefix == "" ? null : format(
    "https://%s.auth.%s.amazoncognito.com/login?client_id=%s&response_type=token&scope=openid+email+profile&redirect_uri=%s",
    aws_cognito_user_pool_domain.this[0].domain,
    var.aws_region,
    aws_cognito_user_pool_client.this.id,
    var.oauth_callback_urls[0],
  )
}

output "demo_user_email" {
  value = var.bootstrap_user_email == "" ? null : var.bootstrap_user_email
}

output "demo_user_password_parameter" {
  value = var.bootstrap_user_email == "" ? null : aws_ssm_parameter.demo_password[0].name
}
