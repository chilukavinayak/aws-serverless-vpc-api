output "api_endpoint" {
  value = module.rest_api.api_endpoint
}

output "user_pool_id" {
  value = module.auth.user_pool_id
}

output "user_pool_client_id" {
  value = module.auth.user_pool_client_id
}

output "table_name" {
  value = module.storage.table_name
}

output "region" {
  value = var.aws_region
}

output "hosted_ui_sign_in_url" {
  value = module.auth.hosted_ui_sign_in_url
}

output "demo_user_email" {
  value = module.auth.demo_user_email
}

output "demo_user_password_parameter" {
  value = module.auth.demo_user_password_parameter
}

output "dashboard_url" {
  value = var.enable_observability ? module.observability[0].dashboard_url : null
}
