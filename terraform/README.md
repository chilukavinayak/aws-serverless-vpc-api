# Terraform

Modular Terraform port of the SAM template. The same code deploys to any
account by exporting that account's credentials and (optionally) pointing at
a different remote backend.

## Layout

```
terraform/
  modules/
    storage/       DynamoDB table + GSI
    auth/          Cognito pool, client, Hosted UI domain, demo user, secret
    lambda-fn/     Reusable single-Lambda module (function + role + log group)
    rest-api/      API Gateway + 4 Lambdas (via lambda-fn) + SSM parameters
  bootstrap/       One-time per account: OIDC provider + deploy role
  main.tf          Root: wires the three top-level modules
  variables.tf     Root inputs (defaults are dev-safe)
  outputs.tf       Root outputs
  versions.tf      Provider + Terraform version constraints
  allianz.auto.tfvars   every value, no defaults
  backend.tf.example
```

## Deploy

```bash
cd terraform
# edit allianz.auto.tfvars; every variable is required and read from it
terraform init
terraform apply
```

Deploy to a different AWS account by exporting different credentials before
running Terraform. Nothing in the code hard-codes an account id. If you want
a second copy in the same account, set a different `environment` value; it
prefixes every resource name.

## Remote state

Local state is fine for a demo. For production, copy `backend.tf.example` to
`backend.tf`, fill in your S3 bucket and DynamoDB lock table, then
`terraform init -reconfigure`.

## Reading outputs

```bash
terraform output api_endpoint
terraform output hosted_ui_sign_in_url
aws secretsmanager get-secret-value \
  --secret-id "$(terraform output -raw demo_user_secret_arn)" \
  --query SecretString --output text
```

Every output is also mirrored into SSM Parameter Store under
`/<environment>/<project_name>/*` (created by the `rest-api` module).

## Module reuse

Each module is self-contained and can be consumed from a different repo:

```hcl
module "vpc_api_auth" {
  source = "git::https://github.com/chilukavinayak/aws-serverless-vpc-api.git//terraform/modules/auth?ref=v1.0.0"

  name_prefix              = "myproject-dev"
  aws_region               = "eu-west-1"
  hosted_ui_domain_prefix  = "myproject-dev"
  bootstrap_user_email     = "demo@example.com"
}
```
