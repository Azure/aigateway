# Lab 13 with Terraform: creates the resource group rg-<environment_name>, the quick start's gateway, Foundry model,
# default alias, and runtime API key, then the Application Insights destination and the OpenTelemetry exporter that
# sends the gateway's metrics, logs, and traces to it (the telemetry module). The runtime API key is never an output.
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

# The quick start's module: a gateway, a Foundry model behind the default alias, and the app-first-call key.
module "base" {
  source = "../../quickstart/terraform/resources"

  subscription_id     = data.azapi_client_config.current.subscription_id
  resource_group_name = azurerm_resource_group.rg.name
  resource_group_id   = azurerm_resource_group.rg.id
  location            = var.location
  tags                = local.tags
  gateway_name        = "aigw-${local.suffix}"
  foundry_name        = "aigw${local.suffix}"
}

# The destination, the role, and the exporter, with the recommended token claims (the module's default).
module "telemetry" {
  source = "./telemetry"

  resource_group_name  = azurerm_resource_group.rg.name
  resource_group_id    = azurerm_resource_group.rg.id
  location             = var.location
  tags                 = local.tags
  gateway_name         = module.base.gateway_name
  gateway_principal_id = module.base.gateway_principal_id
  workspace_id         = module.base.workspace_id
  payload_capture      = var.payload_capture
}
