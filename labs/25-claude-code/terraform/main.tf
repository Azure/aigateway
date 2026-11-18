# Lab 25 with Terraform: publishes the Claude deployments of a Microsoft Foundry account through an existing gateway,
# for Claude Code, like infra/claude-code.bicep. It reads the gateway and the account, and grants the gateway's
# managed identity the Foundry User role on the account (main.tf). Then it creates the provider, the models, the
# aliases with their limits, and the runtime API key (claude-models.tf), and optionally the learn MCP server
# (learn-mcp.tf). It creates no resource group: terraform destroy removes only what this lab added.
data "azapi_client_config" "current" {}

locals {
  foundry_user_role_id    = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  foundry_account_name    = element(split("/", var.foundry_account_id), 8)
  foundry_subscription_id = element(split("/", var.foundry_account_id), 2)
  workspace_id            = "${data.azapi_resource.gateway.id}/workspaces/default"
  gateway_url             = "https://${data.azapi_resource.gateway.output.properties.frontend.defaultHostname}"
}

# The existing gateway, its managed identity, and its runtime host name.
data "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/aigateways@2026-11-01"
  name      = var.gateway_name
  parent_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"

  response_export_values = ["identity.principalId", "properties.frontend.defaultHostname"]
}

# The Foundry account and each Claude deployment, read by resource ID, so the account can be in another resource
# group or subscription. The models record the model and version that Foundry serves.
data "azapi_resource" "foundry" {
  type        = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  resource_id = var.foundry_account_id

  response_export_values = ["properties.endpoint"]
}

data "azapi_resource" "deployment" {
  for_each = { for m in var.claude_models : m.name => m }

  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = each.key
  parent_id = data.azapi_resource.foundry.id

  response_export_values = ["properties.model.name", "properties.model.version"]
}

# Foundry User on the account, so that the gateway can call the deployments with its managed identity. A second
# assignment of the same role fails with RoleAssignmentExists, so grant_foundry_user = false skips it.
resource "azurerm_role_assignment" "foundry_user" {
  count = var.grant_foundry_user ? 1 : 0

  name                             = uuidv5("url", "${var.foundry_account_id}/${data.azapi_resource.gateway.id}/${local.foundry_user_role_id}")
  scope                            = var.foundry_account_id
  role_definition_id               = "/subscriptions/${local.foundry_subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = data.azapi_resource.gateway.output.identity.principalId
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
