# Lab 31 with Terraform: creates the resource group rg-<environment_name> and a gateway with lab 01's module, then
# publishes TypeSafe's Jev decision model (jev-decisions.tf): a Custom provider, the jev-latest model, the
# ticket-triage alias with a request rate limit, and the app-ticket-triage key. No Foundry account is needed. The
# TypeSafe key comes from the ephemeral variable jev_api_key, so it never lands in the plan, the state, or an output.
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

# Lab 01's module: a gateway with a system-assigned managed identity.
module "gateway" {
  source = "../../01-provision-gateway/terraform/gateway"

  gateway_name      = "aigw-${local.suffix}"
  resource_group_id = azurerm_resource_group.rg.id
  location          = var.location
  tags              = local.tags
}
