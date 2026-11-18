# Lab 01 with Terraform: creates the resource group rg-<environment_name>, then calls the gateway module to create
# an AI gateway with a unique name.
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

# The lab's module: the gateway with a system-assigned identity, in the default SKU.
module "gateway" {
  source = "./gateway"

  gateway_name      = "aigw-${local.suffix}"
  resource_group_id = azurerm_resource_group.rg.id
  location          = var.location
  tags              = local.tags
}
