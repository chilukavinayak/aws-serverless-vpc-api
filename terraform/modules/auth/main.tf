data "aws_caller_identity" "current" {}

resource "aws_cognito_user_pool" "this" {
  name = "${var.name_prefix}-users"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = var.password_min_length
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = var.enable_mfa ? "ON" : "OFF"

  dynamic "software_token_mfa_configuration" {
    for_each = var.enable_mfa ? [1] : []
    content {
      enabled = true
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "this" {
  name         = "${var.name_prefix}-client"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code", "implicit"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = var.oauth_callback_urls
  logout_urls                          = var.oauth_callback_urls

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_user_pool_domain" "this" {
  count        = var.hosted_ui_domain_prefix == "" ? 0 : 1
  domain       = "${var.hosted_ui_domain_prefix}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "random_password" "demo" {
  count            = var.bootstrap_user_email == "" ? 0 : 1
  length           = 24
  special          = true
  override_special = "!#$%&*()-_+="
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2

  keepers = {
    email = var.bootstrap_user_email
  }
}

# SSM SecureString (standard tier) is free; Secrets Manager bills per secret.
resource "aws_ssm_parameter" "demo_password" {
  count       = var.bootstrap_user_email == "" ? 0 : 1
  name        = "/${var.ssm_prefix}/demo-user-password"
  type        = "SecureString"
  value       = random_password.demo[0].result
  description = "Cognito demo user password"
  tags        = var.tags
}

resource "aws_cognito_user" "demo" {
  count          = var.bootstrap_user_email == "" ? 0 : 1
  user_pool_id   = aws_cognito_user_pool.this.id
  username       = var.bootstrap_user_email
  password       = random_password.demo[0].result
  message_action = "SUPPRESS"

  attributes = {
    email          = var.bootstrap_user_email
    email_verified = true
  }
}

resource "null_resource" "demo_user_permanent_password" {
  count = var.bootstrap_user_email == "" ? 0 : 1

  triggers = {
    password_hash = sha256(random_password.demo[0].result)
    user_pool_id  = aws_cognito_user_pool.this.id
    email         = var.bootstrap_user_email
  }

  provisioner "local-exec" {
    interpreter = ["/bin/sh", "-c"]
    command     = <<-EOT
      aws cognito-idp admin-set-user-password \
        --user-pool-id "${aws_cognito_user_pool.this.id}" \
        --username     "${var.bootstrap_user_email}" \
        --password     "${random_password.demo[0].result}" \
        --permanent \
        --region       "${var.aws_region}"
    EOT
  }

  depends_on = [aws_cognito_user.demo]
}
