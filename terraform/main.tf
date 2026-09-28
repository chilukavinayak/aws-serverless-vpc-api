provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}

locals {
  name_prefix   = "${var.project_name}-${var.environment}"
  ssm_prefix    = "${var.project_name}/${var.environment}"
  is_production = var.environment == "prod"

  tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    },
    var.extra_tags,
  )

  lambda_env = {
    LOG_LEVEL                    = var.log_level
    POWERTOOLS_METRICS_NAMESPACE = "${var.project_name}/${var.environment}"
    TABLE_NAME                   = module.storage.table_name
    PROJECT_NAME                 = var.project_name
    ENVIRONMENT                  = var.environment
    ALLOWED_VPC_CIDR_PREFIX      = var.allowed_vpc_cidr_prefix
    CUSTOM_METRICS_ENABLED       = tostring(var.enable_custom_metrics)
  }
}

module "storage" {
  source = "./modules/storage"

  table_name             = "${local.name_prefix}-vpcs"
  point_in_time_recovery = var.enable_point_in_time_recovery
  tags                   = local.tags
}

module "auth" {
  source = "./modules/auth"

  name_prefix             = local.name_prefix
  aws_region              = var.aws_region
  password_min_length     = var.cognito_password_min_length
  enable_mfa              = local.is_production
  oauth_callback_urls     = var.oauth_callback_urls
  hosted_ui_domain_prefix = var.cognito_domain_prefix
  bootstrap_user_email    = var.bootstrap_user_email
  ssm_prefix              = local.ssm_prefix
  tags                    = local.tags
}

module "rest_api" {
  source = "./modules/rest-api"

  name_prefix     = local.name_prefix
  aws_region      = var.aws_region
  stage_name      = var.environment
  source_dir      = "${path.module}/../src"
  ssm_prefix      = local.ssm_prefix
  metrics_enabled = var.enable_custom_metrics

  table_arn           = module.storage.table_arn
  table_name          = module.storage.table_name
  user_pool_arn       = module.auth.user_pool_arn
  user_pool_id        = module.auth.user_pool_id
  user_pool_client_id = module.auth.user_pool_client_id

  environment_variables  = local.lambda_env
  lambda_memory_mb       = var.lambda_memory_mb
  lambda_timeout_seconds = var.lambda_timeout_seconds
  log_retention_in_days  = var.log_retention_in_days
  enable_xray_tracing    = var.enable_xray_tracing
  throttle_burst_limit   = var.api_throttle_burst_limit
  throttle_rate_limit    = var.api_throttle_rate_limit

  tags = local.tags
}

module "observability" {
  source = "./modules/observability"
  count  = var.enable_observability ? 1 : 0

  name_prefix    = local.name_prefix
  aws_region     = var.aws_region
  rest_api_id    = module.rest_api.rest_api_id
  rest_api_stage = var.environment
  function_names = values(module.rest_api.function_names)
  table_name     = module.storage.table_name
  alarm_email    = var.alarm_email
  tags           = local.tags
}
