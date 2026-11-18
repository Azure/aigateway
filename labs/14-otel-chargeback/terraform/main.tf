# Lab 14 with Terraform: creates the resource group rg-<environment_name>, the quick start's gateway, Foundry model,
# default alias, and runtime API key, then lab 13's Application Insights destination and OpenTelemetry exporter with
# the token claims to export, and lab 11's role so that you can call the model with your Microsoft Entra token. The
# runtime API key is never an output.
data "azapi_client_config" "current" {}

locals {
  suffix = substr(sha1("${data.azapi_client_config.current.subscription_id}/${var.environment_name}/${var.location}"), 0, 6)
  tags   = { "environment-name" = var.environment_name }

  # The recommended preset exports appid and azp to logs and traces. client_app_metrics adds metrics, so that token
  # and cost metrics can be split by client app.
  client_app_signals = var.client_app_metrics ? ["logs", "traces", "metrics"] : ["logs", "traces"]
  claim_attributes = [
    { claim = "tid", signals = ["logs", "traces", "metrics"] },
    { claim = "oid", signals = ["logs", "traces", "metrics"] },
    { claim = "appid", signals = local.client_app_signals },
    { claim = "azp", signals = local.client_app_signals },
  ]

  # AI Gateway Models User: lets the identity call the gateway's model aliases with a Microsoft Entra token.
  models_user_role_id = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
  principal_id        = coalesce(var.principal_id, data.azapi_client_config.current.object_id)
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

# Lab 13's module: the destination, the role on its Data Collection Rule, and the exporter with the claims above.
module "telemetry" {
  source = "../../13-monitoring/terraform/telemetry"

  resource_group_name  = azurerm_resource_group.rg.name
  resource_group_id    = azurerm_resource_group.rg.id
  location             = var.location
  tags                 = local.tags
  gateway_name         = module.base.gateway_name
  gateway_principal_id = module.base.gateway_principal_id
  workspace_id         = module.base.workspace_id
  claim_attributes     = local.claim_attributes
}

# Lab 11's role assignment: AI Gateway Models User on the gateway, for the Entra calls.
resource "azurerm_role_assignment" "models_user" {
  name                             = uuidv5("url", "${module.base.gateway_id}/${local.principal_id}/${local.models_user_role_id}")
  scope                            = module.base.gateway_id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.models_user_role_id}"
  principal_id                     = local.principal_id
  principal_type                   = var.principal_type
  skip_service_principal_aad_check = var.principal_type == "ServicePrincipal"
}
