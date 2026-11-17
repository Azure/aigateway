# Lab 02 with Terraform: creates the resource group rg-<environment_name> with lab 01's gateway and this lab's
# Foundry account and gpt-5-mini deployment (foundry.tf), then publishes the deployment through the gateway: the
# Foundry User role (foundry-user-role.tf), the model provider, the backend model, the alias, and the
# app-first-call key (publish-model.tf). The runtime API key is never an output.
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
