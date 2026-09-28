# Bootstrap (Terraform flavour)

The same thing as `bootstrap.yaml` at the repo root, for teams that prefer
Terraform. Deploy one or the other per account, not both.

Run once per AWS account with admin credentials. Provisions everything the
CI pipeline needs so no clicks are required in the AWS Console afterwards:

- GitHub Actions OIDC identity provider
- One deploy IAM role, trusted only by workflow runs from `main` of this repo
- (Optional) S3 bucket + DynamoDB lock table for Terraform remote state

## Usage

```bash
cd terraform/bootstrap
# edit bootstrap.auto.tfvars (project, region, repository, owner id, repository id, branch)
terraform init
terraform apply
```

`bootstrap.auto.tfvars` is the only place any value is configured;
there are no defaults in `variables.tf`, so a wrong or missing value fails at
plan time instead of producing a role nobody can assume. Owner and repository
ids come from `https://api.github.com/users/<owner>` and
`https://api.github.com/repos/<owner>/<repo>`.

Copy the `deploy_role_arn` output into GitHub as a repository secret named
`AWS_DEPLOY_ROLE_ARN` (**Settings → Secrets and variables → Actions**).
That is the only secret the pipeline needs.

## Moving to another AWS account

Export credentials for the new account, run the same `terraform apply`, then
update the `AWS_DEPLOY_ROLE_ARN` secret with the new role ARN. If the GitHub
side changed too, edit `bootstrap.auto.tfvars` first. Nothing in the code
hard-codes an account id.

## Enable remote state (optional)

```bash
terraform apply -var="state_bucket_name=my-org-tfstate-us-east-1"
```

Then in the main Terraform stack:

```hcl
# terraform/backend.tf
terraform {
  backend "s3" {
    bucket         = "my-org-tfstate-us-east-1"
    key            = "allianz-vpc-provisioner/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "allianz-vpc-provisioner-tfstate-lock"
    encrypt        = true
  }
}
```
