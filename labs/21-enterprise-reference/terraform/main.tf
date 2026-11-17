# Lab 21 with Terraform: the enterprise reference environment that infra/main.bicep deploys, as a root module that
# wires the modules in modules/ together. Pick the environment with a variable file:
#   terraform plan -var-file dev.tfvars -out tfplan
# It creates two resource groups, rg-<environment_name>-gateway and rg-<environment_name>-foundrymodels, then the
# monitoring, the Foundry models, the gateway, the backend model and its alias, the MCP server, one runtime API key
# per app, and the OpenTelemetry exporter. The runtime API keys are never outputs.
data "azapi_client_config" "current" {}

locals {
  suffix              = substr(sha1("${data.azapi_client_config.current.subscription_id}/${var.environment_name}/${var.location}"), 0, 6)
  ai_gateway_location = var.ai_gateway_location != "" ? var.ai_gateway_location : var.location
  ai_gateway_name     = var.ai_gateway_name != "" ? var.ai_gateway_name : "aigw-${local.suffix}"
  tags = merge({
    "environment-name" = var.environment_name
    workload           = "ai-gateway"
  }, var.tags)

  # The developer from principal_id, when set, gets data-plane access next to the Entra groups of the environment.
  developer = var.principal_id == "" ? [] : [{ principal_id = var.principal_id, principal_type = "User" }]
}

resource "azurerm_resource_group" "gateway" {
  name     = "rg-${var.environment_name}-gateway"
  location = var.location
  tags     = local.tags
}

resource "azurerm_resource_group" "foundry_models" {
  name     = "rg-${var.environment_name}-foundrymodels"
  location = var.location
  tags     = local.tags
}

# Log Analytics and Application Insights, with OTLP ingestion on, in the gateway's resource group.
module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name = azurerm_resource_group.gateway.name
  resource_group_id   = azurerm_resource_group.gateway.id
  location            = var.location
  tags                = local.tags
  workspace_name      = substr("${local.ai_gateway_name}-logs", 0, 63)
  app_insights_name   = substr("${local.ai_gateway_name}-insights", 0, 64)
  retention_in_days   = var.log_retention_in_days
}

# The Foundry account and its model deployment, in their own resource group.
module "foundry" {
  source = "./modules/foundry"

  resource_group_name = azurerm_resource_group.foundry_models.name
  location            = var.location
  tags                = local.tags
  name                = "aimodels-${local.suffix}"
  principal_id        = var.principal_id
  model_deployments = {
    (var.model_deployment_name) = {
      model_name    = var.model_name
      model_format  = var.model_format
      model_version = var.model_version
      sku_name      = var.model_sku_name
      capacity      = var.model_capacity
    }
  }
}

# The gateway, with the Foundry User role on the account for its managed identity.
module "gateway" {
  source = "./modules/gateway"

  resource_group_id    = azurerm_resource_group.gateway.id
  location             = local.ai_gateway_location
  tags                 = local.tags
  gateway_name         = local.ai_gateway_name
  foundry_resource_ids = [module.foundry.id]
}

# The Foundry provider, the backend model with its token limit and content safety, the alias, and who can call it.
module "models" {
  source = "./modules/models"

  gateway_id           = module.gateway.id
  provider_description = "Managed-identity Foundry provider for the ${var.environment_name} environment."
  foundry_endpoint     = module.foundry.endpoint
  foundry_resource_ids = [module.foundry.id]
  models = {
    (var.model_deployment_name) = {
      description   = "Default chat model for every app behind the gateway."
      resource_id   = module.foundry.deployment_ids[var.model_deployment_name]
      model_name    = var.model_name
      model_version = var.model_version
      token_limit   = var.tokens_per_minute_per_caller
      supported_endpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
    }
  }
  content_safety_severity = var.content_safety_severity
  alias_name              = var.alias_name
  alias_model             = var.model_deployment_name
  alias_users             = concat(local.developer, var.model_users)

  depends_on = [module.gateway]
}

# The Microsoft Learn MCP server, and who can call it.
module "tools" {
  source = "./modules/tools"

  gateway_id       = module.gateway.id
  gateway_hostname = module.gateway.hostname
  tool_users       = concat(local.developer, var.tool_users)
}

# One runtime API key per app. Read a key with az aigateway api-key list-secrets.
module "keys" {
  source = "./modules/keys"

  gateway_id = module.gateway.id
  app_names  = var.app_names
}

# The OpenTelemetry exporter to Application Insights. The Bicep track deploys it with scripts/connect-telemetry.sh,
# because Bicep can't wait for the OTLP endpoints. Terraform waits for them, assigns the role, and creates the
# exporter in the same apply.
module "telemetry" {
  source = "./modules/telemetry"

  gateway_id           = module.gateway.id
  gateway_principal_id = module.gateway.principal_id
  app_insights_id      = module.monitoring.app_insights_id
}
