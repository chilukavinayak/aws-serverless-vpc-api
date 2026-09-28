# Every value comes from samconfig.toml; nothing here has a default.
CFG      := samconfig.toml
_param    = $(shell python3 -c 'import tomllib,re,sys; d=tomllib.load(open("$(CFG)","rb")); o=d["default"]["deploy"]["parameters"]["parameter_overrides"]; m=re.search(r"\b$(1)=(\S+)", o); print(m.group(1) if m else "")')
_global   = $(shell python3 -c 'import tomllib; print(tomllib.load(open("$(CFG)","rb"))["default"]["global"]["parameters"].get("$(1)",""))')
PROJECT  := $(call _param,ProjectName)
ENV      := $(call _param,Environment)
STACK    := $(call _global,stack_name)
REGION   := $(call _global,region)
$(if $(PROJECT),,$(error ProjectName is missing from $(CFG) parameter_overrides))
$(if $(ENV),,$(error Environment is missing from $(CFG) parameter_overrides))
$(if $(STACK),,$(error stack_name is missing from $(CFG) [default.global.parameters]))
$(if $(REGION),,$(error region is missing from $(CFG) [default.global.parameters]))

CFN_OUTPUT = aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
               --query "Stacks[0].Outputs[?OutputKey=='$(1)'].OutputValue" --output text

.DEFAULT_GOAL := help

.PHONY: help install-dev bootstrap validate build deploy destroy \
        test coverage test-int lint format \
        outputs api-endpoint hosted-ui demo-password ssm-list clean

help:
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install-dev:           ## Install dev/test deps into the active venv
	python -m pip install -r requirements-dev.txt

bootstrap:             ## One-time per account: OIDC provider + deploy role (every value from bootstrap.params.json)
	aws cloudformation deploy --template-file bootstrap.yaml --stack-name $(PROJECT)-bootstrap \
		--capabilities CAPABILITY_NAMED_IAM --region $(REGION) \
		--parameter-overrides file://bootstrap.params.json
	@aws cloudformation describe-stacks --stack-name $(PROJECT)-bootstrap --region $(REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" --output text

validate:              ## sam validate --lint
	sam validate --lint

build:                 ## sam build
	sam build --cached --parallel

deploy: build          ## sam deploy (every value from samconfig.toml)
	sam deploy $(if $(PARAMS),--parameter-overrides $(PARAMS),)

destroy:               ## sam delete for $(STACK)
	sam delete --stack-name $(STACK) --region $(REGION) --no-prompts

outputs:               ## Print every stack output
	aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
		--query 'Stacks[0].Outputs' --output table

api-endpoint:          ## Print ApiEndpoint
	@$(call CFN_OUTPUT,ApiEndpoint)

hosted-ui:             ## Print Cognito Hosted UI sign-in URL
	@$(call CFN_OUTPUT,HostedUiSignInUrl)

demo-password:         ## Print demo user password from SSM (SecureString)
	@aws ssm get-parameter --name "/$(PROJECT)/$(ENV)/demo-user-password" \
		--with-decryption --region $(REGION) --query Parameter.Value --output text

ssm-list:              ## List every SSM param under /$(PROJECT)/$(ENV)/
	aws ssm get-parameters-by-path --path /$(PROJECT)/$(ENV)/ --region $(REGION) \
		--query 'Parameters[].[Name,Value]' --output table

test:                  ## Unit tests (offline, moto)
	pytest -q -m "not integration"

coverage:              ## Unit tests with coverage
	pytest --cov=src --cov-report=term-missing -m "not integration"

test-int:              ## End-to-end test against a deployed stack
	STACK_NAME=$(STACK) AWS_REGION=$(REGION) pytest -q -m integration

lint:                  ## ruff check
	ruff check src tests

format:                ## ruff format
	ruff format src tests

clean:                 ## Remove build/test artifacts
	rm -rf .aws-sam .pytest_cache .coverage coverage.xml htmlcov
	find . -name '__pycache__' -type d -exec rm -rf {} +
