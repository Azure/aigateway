# Lab 17's migration with Terraform: the AI Gateway that the settled plan.json describes for the sample source
# (infra/apim-source.bicep). It creates the resource group rg-<environment_name> with lab 01's gateway, then what
# the plan maps (migrated-gateway.tf): the Foundry User role on the source's Foundry account, the model provider,
# the model with its token limit, the alias, the MCP server, and the ticket-app key. Compare it with what your
# coding agent writes from your own plan. The runtime API key is never an output.
data "azapi_client_config" "current" {}

locals {
  suffix = substr(sha1("${data.azapi_client_config.current.subscription_id}/${var.environment_name}/${var.location}"), 0, 6)
  tags   = { "environment-name" = var.environment_name }
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.environment_name}"
  location = var.location
  tags     = local.tags
}

# Lab 01's module: the gateway with a system-assigned identity.
module "gateway" {
  source = "../../01-provision-gateway/terraform/gateway"

  gateway_name      = "aigw-${local.suffix}"
  resource_group_id = azurerm_resource_group.rg.id
  location          = var.location
  tags              = local.tags
}
