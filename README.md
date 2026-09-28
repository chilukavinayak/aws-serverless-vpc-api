# aws-serverless-vpc-api

Serverless REST API that creates AWS VPCs with N subnets, stores the metadata
in DynamoDB, and lets authenticated users retrieve it. Written in Python for
AWS Lambda; auth via Amazon Cognito.

## Stack

- API Gateway (REST) — routing + Cognito JWT authorizer
- Lambda (Python 3.12, arm64) — one function per endpoint
- DynamoDB (on-demand) — stores VPC records, GSI for per-owner listing
- Cognito User Pool — authentication (Hosted UI optional)
- SSM Parameter Store (SecureString) — holds the demo user password
- SSM Parameter Store — mirrors stack outputs
- CloudWatch Logs — 14-day retention, EMF metrics

Two IaC implementations of the same infrastructure:

- `template.yaml` — AWS SAM (primary)
- `terraform/` — Terraform port

## Endpoints

| Method | Path              | Purpose                                           | Success |
|--------|-------------------|---------------------------------------------------|---------|
| POST   | `/vpcs`           | Create a VPC with 1–20 subnets                    | 201     |
| GET    | `/vpcs`           | List VPCs, paginated (`scope=mine\|all`, `limit`, `cursor`) | 200 |
| GET    | `/vpcs/{vpc_id}`  | Fetch one VPC record                              | 200     |
| DELETE | `/vpcs/{vpc_id}`  | Delete the AWS resources and the record           | 204     |

Every route requires `Authorization: <Cognito ID token>`. The full contract is
`openapi.yaml`; a Postman collection with a sign-in request and edge-case
requests is `postman/allianz-vpc-provisioner.postman_collection.json`.

## How it works

1. **Authenticate.** The caller signs in to the Cognito user pool and sends the
   ID token. API Gateway validates it before any Lambda runs; a missing or bad
   token is answered `401` by the gateway itself.
2. **Validate.** `POST /vpcs` is parsed into a typed request. Name, CIDR,
   every subnet and every tag are checked (rules below). Any failure is `400
   validation_error` with the field named in the message.
3. **Check for overlap.** The VPC CIDR is compared with the CIDR of every
   record in DynamoDB that is not `DELETED`. An overlap is `409 conflict` with
   the existing VPC id and CIDR in `details`.
4. **Provision.** A record is written with status `CREATING`, then EC2 calls
   run in order: create VPC, wait until available, enable DNS support and
   hostnames, create each subnet (round-robin across the region's available
   AZs when none is given; `map_public_ip_on_launch` for `is_public`). Every
   resource carries `Project`, `Environment`, `ManagedBy`, `InternalVpcId`,
   `OwnerId` and the caller's tags.
5. **Persist.** The record becomes `ACTIVE` with the AWS ids and the subnet
   list, and is returned with `201`.
6. **Delete.** `DELETE` marks the record `DELETING`, deletes the subnets then
   the VPC, then removes the record. AWS resources are matched by the
   `ManagedBy` tag, so the API's IAM policy cannot touch a VPC it did not
   create.

The functions never create internet gateways, NAT gateways, route tables or
Elastic IPs, so nothing created by the API costs money.

## Request body — POST /vpcs

```json
{
  "name": "sandbox-vpc",
  "cidr_block": "10.20.0.0/16",
  "subnets": [
    {"cidr_block": "10.20.1.0/24", "availability_zone": "us-east-1a", "name": "public-web", "is_public": true},
    {"cidr_block": "10.20.2.0/24", "name": "private-app"}
  ],
  "tags": {"CostCenter": "R&D"}
}
```

## Validation rules and edge cases

| Input / situation                                   | Behaviour                                                     |
|-----------------------------------------------------|---------------------------------------------------------------|
| `name` missing, empty, > 64 chars, or not `[A-Za-z0-9 _.-]` | `400`                                                  |
| `cidr_block` not IPv4, not a network address (`10.0.0.1/16`), or outside `/16`–`/28` | `400`                       |
| `cidr_block` not starting with `AllowedVpcCidrPrefix` (`10.` by default) | `400`, platform policy                       |
| `cidr_block` overlaps any non-deleted VPC in the table | `409 conflict`, existing id and CIDR returned            |
| `subnets` missing, empty, or more than 20            | `400`                                                         |
| Subnet CIDR outside the VPC CIDR, or outside `/16`–`/28` | `400`                                                     |
| Two subnets with the same CIDR                      | `400`                                                         |
| Subnet `availability_zone` omitted                  | Assigned round-robin across available AZs                     |
| Subnet `name` omitted                               | `<vpc-name>-subnet-<n>`                                       |
| More than 25 tags, key not matching AWS tag rules, value > 256 chars | `400`                                         |
| Subnet creation fails midway                        | Created subnets and the VPC are deleted best-effort, record marked `FAILED`, `502 upstream_error` |
| No AZ available in the region                       | `400`                                                         |
| `GET /vpcs/{id}` for an unknown id                  | `404 not_found`                                               |
| `DELETE` for an unknown id                          | `204`, idempotent                                             |
| `DELETE` while the VPC has other resources (ENIs, instances) | `409 conflict`, record returns to `ACTIVE`             |
| `GET /vpcs?limit=` outside 1–100 or not an integer  | `400`                                                         |
| `GET /vpcs?scope=` other than `mine` or `all`       | `400`                                                         |
| Request rate above the throttle                     | `429` from API Gateway, no Lambda invoked                     |
| Any unhandled AWS error                             | `502 upstream_error`, details in CloudWatch Logs              |

Every error body has the same shape: `{"error": "<code>", "message": "<text>", "details": {...}}`.

## Limits

| Limit                                  | Value | Where it comes from |
|----------------------------------------|-------|---------------------|
| API rate                               | 10 requests/min (rate 0.17/s, burst 10) | `ApiThrottleRateLimit`, `ApiThrottleBurstLimit` in `samconfig.toml` |
| VPCs per region                        | 5 by default | AWS account quota; raise it in Service Quotas to onboard more |
| Subnets per VPC via this API           | 20    | `MAX_SUBNETS` in the validator; AWS allows 200 |
| VPC / subnet CIDR size                 | `/16` to `/28` | AWS |
| Tags per request                       | 25    | validator; AWS allows 50 per resource |
| List page size                         | 25 default, 100 max | `GET /vpcs?limit=` |
| Users                                  | admin-created only, no self sign-up; 10,000 monthly active users free | Cognito `AllowAdminCreateUserOnly` |
| Time to create one VPC                 | under the 30 s Lambda timeout for 20 subnets | `LambdaTimeoutSeconds` |
| Database throughput                    | 5 reads/s, 5 writes/s | `template.yaml`, always-free tier |
| Records                                | practically unbounded; 25 GB free | DynamoDB |

Known limitations, on purpose for an assignment:

- Any authenticated user can read or delete any VPC; `scope=all` lists every
  record. Per-user ownership is stored (`owner_id`) but not enforced.
- Two simultaneous `POST /vpcs` with overlapping CIDRs can both pass the
  overlap check. A conditional write would close this.
- The overlap check scans the whole table; fine for hundreds of records.
- One environment, one region. Nothing hard-codes the account, so a second
  copy is a second `samconfig.toml`.

## Deploy — SAM

```bash
# every value lives in samconfig.toml; nothing has a default
make deploy
make hosted-ui         # print Cognito Hosted UI sign-in URL
make demo-password     # print the demo user's password (SSM SecureString)
```

## Deploy — Terraform

```bash
cd terraform
# every value lives in allianz.auto.tfvars; nothing has a default
terraform init && terraform apply
```

## Moving to another AWS account

Nothing hard-codes an account id or region. Export credentials for the
target account and run either deploy above. For CI, run
`make bootstrap` once in that account (deploys `bootstrap.yaml` with the
values in `bootstrap.params.json`; the console "Create stack" upload or
`terraform/bootstrap` work too) and put the printed `DeployRoleArn` into the
single `AWS_DEPLOY_ROLE_ARN` repository secret. The GitHub repository, owner
id, repository id and branch the role trusts live only in
`bootstrap.params.json` (CloudFormation) and
`terraform/bootstrap/bootstrap.auto.tfvars` (Terraform); edit those and re-run
whenever they change. The role is
least-privilege: it can only create, change or delete resources whose names
start with `allianz-vpc-provisioner-`. No IAM users or access keys are ever created.

## Tests

```bash
make test          # unit tests (moto, offline)
make coverage      # with coverage report
make test-int      # end-to-end against a deployed stack
```

48 tests, ~85 % line coverage.

## Layout

```
src/
  handlers/     one file per endpoint (thin)
  services/    all boto3 calls (EC2, DynamoDB)
  models/      dataclasses
  validators/  request validation + CIDR overlap check
  exceptions/  ApiError → HTTP status
  utils/       logger, config, responses, metrics
tests/
  unit/        offline, moto-mocked
  integration/ live smoke test
terraform/    Terraform port (modular)
  modules/{storage,auth,lambda-fn,rest-api,observability}
  bootstrap/  one-time per account: OIDC provider + deploy role
  allianz.auto.tfvars   every Terraform value, no defaults
openapi.yaml  OpenAPI 3 contract
postman/      Postman collection
template.yaml SAM template
Makefile      make targets that wrap sam / aws / pytest
```

## Naming convention

Every resource, in both SAM and Terraform, is named
`{project}-{environment}-{component}` with lowercase words separated by
dashes. `project` defaults to `allianz-vpc-provisioner`, `environment` to `dev`, so a default
deployment produces:

| Resource                | Name                                  |
|-------------------------|---------------------------------------|
| CloudFormation stack    | `allianz-vpc-provisioner-dev`                         |
| REST API                | `allianz-vpc-provisioner-dev-api`                     |
| Lambda functions        | `allianz-vpc-provisioner-dev-create-vpc`, `-get-vpc`, `-list-vpcs`, `-delete-vpc`, `-user-bootstrap` |
| Log groups              | `/aws/lambda/allianz-vpc-provisioner-dev-create-vpc` etc. |
| DynamoDB table          | `allianz-vpc-provisioner-dev-vpcs`                    |
| Cognito user pool       | `allianz-vpc-provisioner-dev-users`                   |
| Cognito app client      | `allianz-vpc-provisioner-dev-client`                  |
| Cognito Hosted UI       | `allianz-vpc-provisioner-dev-<account-id>`            |
| Demo user password      | SSM SecureString `/allianz-vpc-provisioner/dev/demo-user-password` |
| SSM parameters          | `/allianz-vpc-provisioner/dev/api-endpoint`, `/user-pool-id`, `/user-pool-client-id`, `/table-name` |
| CloudWatch namespace    | `allianz-vpc-provisioner/dev`                         |
| Alarms / dashboard      | `allianz-vpc-provisioner-dev-api-5xx`, `allianz-vpc-provisioner-dev-dashboard` |
| CI deploy role          | `allianz-vpc-provisioner-deploy` (per account, no environment; may only touch `allianz-vpc-provisioner-*` resources) |

Every resource also carries the tags `Project`, `Environment` and
`ManagedBy`. VPCs and subnets created *by* the API get the same three tags
plus `InternalVpcId` and `OwnerId`; their `Name` tag is the caller-supplied
name, and subnets default to `<vpc-name>-subnet-<n>`. The IAM policies that
let the API modify or delete EC2 resources are conditioned on
`ManagedBy = {project}`, so the API can only touch what it created.

## Observability (Terraform, opt-in)

Set `enable_observability = true` in `allianz.auto.tfvars` and Terraform
provisions a CloudWatch dashboard plus alarms for:

- any Lambda `Errors > 0` in a 5-minute window
- API Gateway 5xx rate above the configured threshold (default 1 %)
- DynamoDB read throttling

Set `alarm_email` to also receive SNS notifications.

## Configuration

Every value is a SAM parameter / Terraform variable and **none has a
default**. The values live in exactly one place per tool:

| Tool           | File                                     | Missing a value fails with          |
|----------------|------------------------------------------|-------------------------------------|
| SAM            | `samconfig.toml`                         | the parameter name, from CloudFormation |
| Terraform      | `terraform/allianz.auto.tfvars`          | "No value for required variable"    |
| Bootstrap (CFN)| `bootstrap.params.json`                  | the parameter name, from CloudFormation |
| Bootstrap (TF) | `terraform/bootstrap/bootstrap.auto.tfvars` | "No value for required variable" |
| Makefile       | reads `samconfig.toml`                   | `make` errors naming the key        |
| Lambda code    | environment set by the template          | RuntimeError naming the variable    |

Nothing is hardcoded to an account or region.

Key parameters:

| Name                     | Default | Notes                                          |
|--------------------------|---------|------------------------------------------------|
| `ProjectName`            | allianz-vpc-provisioner | Prefix for physical resource names             |
| `Environment`            | dev     | Also drives log retention and MFA defaults     |
| `LambdaMemoryMB`         | 512     | arm64                                          |
| `LogRetentionInDays`     | 14      |                                                |
| `AllowedVpcCidrPrefix`   | `10.`   | Reject VPC CIDRs outside this prefix (set `""` to disable) |
| `CognitoDomainPrefix`    | `""`    | Non-empty enables the Hosted UI                |
| `BootstrapUserEmail`     | `""`    | Non-empty creates a demo user during deploy    |
| `EnableCustomMetrics`    | `false` | EMF + API Gateway detailed metrics (billable beyond 10 free) |

## CI/CD

`.github/workflows/ci.yml` is deliberately compact: three runners per pull
request, each doing several things after a single checkout and tool setup,
so a PR is not paying 15 times for runner start-up.

| Job         | Runs                                                                 |
|-------------|----------------------------------------------------------------------|
| `python`    | ruff (lint + format), bandit, gitleaks, pytest with coverage         |
| `terraform` | `fmt -check`, `validate`, tfsec, checkov                             |
| `sam`       | `sam validate --lint`, cfn-nag, checkov, `sam build` (artifact)      |
| `deploy`    | On pushes to `main`: `sam deploy`, then the Postman collection via newman (every request and error code) and the pytest end-to-end test. Terraform is validated only; deploy it by hand, never alongside the SAM stack in the same account. |

Doc-only changes (`*.md`, `postman/`, `examples/`, `openapi.yaml`) skip CI.
Pip, Terraform provider and SAM build caches are keyed on their lock/spec
files. To add a manual approval gate later, attach the `deploy` job to a
GitHub Environment with *Required reviewers*.

`.pre-commit-config.yaml` runs the same lint/secret/security checks locally
before each commit (`pre-commit install` once).

### Required GitHub secret

One repository secret (**Settings → Secrets and variables → Actions**):

| Secret                | Purpose                                                  |
|-----------------------|----------------------------------------------------------|
| `AWS_DEPLOY_ROLE_ARN` | IAM role assumed via OIDC; created once per account by `bootstrap.yaml` (or `terraform/bootstrap`) |

**No long-lived AWS keys are stored in GitHub.** Deploy jobs request an OIDC
token (`id-token: write`) and exchange it via `sts:AssumeRoleWithWebIdentity`;
credentials expire when the job ends.

The IAM role trust policy on the AWS side should look like:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": [
          "repo:<owner>/<repo>:ref:refs/heads/main",
          "repo:<owner>@<owner-id>/<repo>@<repo-id>:ref:refs/heads/main"
        ]
      }
    }
  }]
}
```

## Cost

Designed to run inside the always-free tier, not just the 12-month one:

| Service            | Choice                                              | Free tier used                      |
|--------------------|-----------------------------------------------------|-------------------------------------|
| Lambda             | arm64, 512 MB                                       | 1M requests + 400k GB-s / month     |
| DynamoDB           | provisioned 5 RCU / 5 WCU on table and index, no PITR | 25 RCU / 25 WCU / 25 GB always free |
| Cognito            | no advanced security, MFA off outside `prod`        | 10 000 MAU                          |
| API Gateway (REST) | detailed metrics off                                | 1M calls / month for 12 months, then $3.50 per million |
| CloudWatch Logs    | 14-day retention                                    | 5 GB ingest / month                 |
| CloudWatch metrics | EMF custom metrics off by default                   | standard metrics are free           |
| SSM Parameter Store| standard-tier SecureString for the demo password    | free                                |
| S3                 | one SAM artifact bucket                             | 5 GB for 12 months, then cents      |
| X-Ray, alarms, dashboards, SNS | all off by default                      | —                                   |

Nothing in the stack bills while idle. The only line item that can ever
appear is API Gateway requests after the first-year free tier, and a
reviewer's traffic stays far below one rupee. VPCs and subnets created by the
API are free; the service never creates NAT gateways or Elastic IPs.
