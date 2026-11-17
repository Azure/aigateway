# Lab 12 with Terraform: creates the resource group rg-<environment_name>, the quick start's gateway, Foundry model,
# default alias, and runtime API key, then your user-assigned identity with Foundry User on the Foundry account
# (backend-identity.tf). Set use_user_assigned_identity to true to point the Foundry provider at the identity
# (model-provider.tf). The runtime API key is never an output.
#
# The quick start's module declares the gateway with only its system-assigned identity, and the gateway keeps only
# the identities that its identity block lists. So this lab declares the module's resources itself, with a gateway
# that lists both identities.
data "azapi_client_config" "current" {}

locals {
  suffix               = substr(sha1("${data.azapi_client_config.current.subscription_id}/${var.environment_name}/${var.location}"), 0, 6)
  tags                 = { "environment-name" = var.environment_name }
  gateway_name         = "aigw-${local.suffix}"
  foundry_name         = "aigw${local.suffix}"
  model_name           = "gpt-5-mini"
  model_version        = "2025-08-07"
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  workspace_id         = "${azapi_resource.gateway.id}/workspaces/default"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.environment_name}"
  location = var.location
  tags     = local.tags
}

# The gateway, with its system-assigned identity and your user-assigned identity. It omits sku, so it gets the
# default SKU.
resource "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/aigateways@2026-11-01"
  name      = local.gateway_name
  parent_id = azurerm_resource_group.rg.id
  location  = var.location
  tags      = local.tags

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.backends.id]
  }

  body = {
    properties = {}
  }

  schema_validation_enabled = false
  response_export_values    = ["properties.frontend.defaultHostname"]

  # Activation can take longer than azapi's default 30 minutes in some regions.
  timeouts {
    create = "60m"
  }
}

# A Foundry account with one model deployment. Local auth is off: only Entra identities can call it.
resource "azurerm_cognitive_account" "foundry" {
  name                  = local.foundry_name
  resource_group_name   = azurerm_resource_group.rg.name
  location              = var.location
  tags                  = local.tags
  kind                  = "AIServices"
  sku_name              = "S0"
  custom_subdomain_name = local.foundry_name
  local_auth_enabled    = false
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = local.model_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  model {
    format  = "OpenAI"
    name    = local.model_name
    version = local.model_version
  }
}

# The quick start's provider calls Foundry with the gateway's system-assigned identity, which needs Foundry User too.
resource "azurerm_role_assignment" "gateway_foundry_user" {
  name                             = uuidv5("url", "${azurerm_cognitive_account.foundry.id}/${azapi_resource.gateway.id}/${local.foundry_user_role_id}")
  scope                            = azurerm_cognitive_account.foundry.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = azapi_resource.gateway.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# The deployment as a backend model of the provider, and an alias that apps send in the "model" field.
resource "azapi_resource" "model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = local.model_name
  parent_id = azapi_resource.provider.id

  body = {
    properties = {
      displayName = local.model_name
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.model.id
        modelName    = local.model_name
        modelVersion = local.model_version
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = local.model_name
  parent_id = local.workspace_id

  body = {
    properties = {
      aliasName = local.model_name
      backendModels = [
        {
          resourceId = azapi_resource.model.id
        },
      ]
    }
  }

  schema_validation_enabled = false
}

# The app-first-call key. Read its value with az aigateway api-key list-secrets.
resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = "app-first-call"
  parent_id = azapi_resource.gateway.id

  body = {
    properties = {
      displayName = "app-first-call"
    }
  }

  schema_validation_enabled = false
}
