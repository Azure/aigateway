# Production environment, like infra/prod.bicepparam. Same configuration, different values: no developer access,
# more capacity, longer retention, and access granted to Microsoft Entra groups instead of individuals. Replace the
# placeholder group object IDs. Plan it with:
#   terraform plan -var-file prod.tfvars -out tfplan
environment_name = "aigw-prod-tf"
principal_id     = ""

model_capacity               = 200
tokens_per_minute_per_caller = 50000
content_safety_severity      = "Medium"
alias_name                   = "chat"

app_names = [
  "web-chat",
  "batch-jobs",
]

model_users = [
  # {
  #   principal_id   = "<object-id-of-the-model-users-group>"
  #   principal_type = "Group"
  # },
]

tool_users = [
  # {
  #   principal_id   = "<object-id-of-the-tool-users-group>"
  #   principal_type = "Group"
  # },
]

log_retention_in_days = 90

tags = {
  costCenter = "platform"
}
