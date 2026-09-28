# Every Terraform value. Nothing in variables.tf has a default.
project_name = "allianz-vpc-provisioner"
environment  = "dev"
aws_region   = "us-east-1"

log_level              = "INFO"
log_retention_in_days  = 14
lambda_memory_mb       = 512
lambda_timeout_seconds = 30

enable_xray_tracing           = false
enable_point_in_time_recovery = false
enable_custom_metrics         = false
enable_observability          = false
alarm_email                   = ""

api_throttle_burst_limit = 10
api_throttle_rate_limit  = 0.17
allowed_vpc_cidr_prefix  = "10."

cognito_password_min_length = 12
cognito_domain_prefix       = "allianz-vpc-provisioner-dev"
oauth_callback_urls         = ["https://oauth.pstmn.io/v1/callback"]
bootstrap_user_email        = "demo@example.com"

extra_tags = {}
