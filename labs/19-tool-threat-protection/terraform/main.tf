# Lab 19 with Terraform: creates the resource group rg-<environment_name>, a gateway with lab 01's module, then the
# learn MCP server, the AI Gateway Tools User role on it for the signed-in user, and the runtime API key
# app-first-call (tool-server.tf). The tool threat protection stages are off until you turn them on with -var.
# The runtime API key is never an output.
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

# Lab 01's module: the gateway, with no model.
module "gateway" {
  source = "../../01-provision-gateway/terraform/gateway"

  gateway_name      = "aigw-${local.suffix}"
  resource_group_id = azurerm_resource_group.rg.id
  location          = var.location
  tags              = local.tags
}
