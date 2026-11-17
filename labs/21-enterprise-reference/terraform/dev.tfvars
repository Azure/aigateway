# Development environment, like infra/main.bicepparam. Plan it with:
#   terraform plan -var-file dev.tfvars -out tfplan
# Set TF_VAR_principal_id to your object ID (az ad signed-in-user show --query id -o tsv) to get developer access.
# The file doesn't set location, so TF_VAR_location or -var location=<region> picks the region.
environment_name = "aigw-dev-tf"

model_capacity               = 50
tokens_per_minute_per_caller = 20000
content_safety_severity      = "Medium"
alias_name                   = "chat"

app_names = [
  "web-chat",
  "batch-jobs",
]

log_retention_in_days = 30

tags = {
  costCenter = "dev"
}
