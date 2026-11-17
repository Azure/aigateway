# The building blocks of the quick start, the same ones that the portal, Azure CLI, and Bicep tracks create:
# a gateway, a Foundry model deployment, a model provider that signs in with the gateway's managed identity,
# an alias that apps send in the "model" field, and a runtime API key. The labs reuse this module.
terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

locals {
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  workspace_id         = "${azapi_resource.gateway.id}/workspaces/default"
}

# 1. The gateway, with a system-assigned managed identity. It omits sku, so it gets the default SKU. AI Gateway
#    resources have no Terraform schema yet, so azapi sends the body as is.
resource "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/aigateways@2026-11-01"
  name      = var.gateway_name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = var.tags

  identity {
    type = "SystemAssigned"
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

# 2. A Foundry account with one model deployment. Local auth is off: only Entra identities can call it.
resource "azurerm_cognitive_account" "foundry" {
  name                  = var.foundry_name
  resource_group_name   = var.resource_group_name
  location              = var.location
  tags                  = var.tags
  kind                  = "AIServices"
  sku_name              = "S0"
  custom_subdomain_name = var.foundry_name
  local_auth_enabled    = false
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = var.model_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = var.capacity
  }

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }
}

# The gateway calls Foundry with its own identity, so it needs the Foundry User role on the account.
resource "azurerm_role_assignment" "foundry_user" {
  name                             = uuidv5("url", "${azurerm_cognitive_account.foundry.id}/${azapi_resource.gateway.id}/${local.foundry_user_role_id}")
  scope                            = azurerm_cognitive_account.foundry.id
  role_definition_id               = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = azapi_resource.gateway.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# 3. A model provider that points at the Foundry account and signs in with the managed identity.
resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = var.provider_name
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Foundry"
      displayName       = "Foundry models"
      foundry = {
        endpoint = {
          url = "https://${var.foundry_name}.cognitiveservices.azure.com/"
        }
        resourceIds = [azurerm_cognitive_account.foundry.id]
      }
      authentication = {
        managedIdentity = {
          resource = "https://cognitiveservices.azure.com/"
        }
      }
    }
  }

  schema_validation_enabled = false
  depends_on                = [azurerm_role_assignment.foundry_user]
}

# 4. The deployment as a backend model, and an alias that apps send in the "model" field.
resource "azapi_resource" "model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = var.model_name
  parent_id = azapi_resource.provider.id

  body = {
    properties = {
      displayName = var.model_name
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.model.id
        modelName    = var.model_name
        modelVersion = var.model_version
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = var.model_name
  parent_id = local.workspace_id

  body = {
    properties = {
      aliasName = var.model_name
      backendModels = [
        {
          resourceId = azapi_resource.model.id
        },
      ]
    }
  }

  schema_validation_enabled = false
}

# 5. A runtime API key for your first app. Read its value with az aigateway api-key list-secrets; it's never an
#    output, so it stays out of the Terraform state.
resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = var.api_key_name
  parent_id = azapi_resource.gateway.id

  body = {
    properties = {
      displayName = var.api_key_name
    }
  }

  schema_validation_enabled = false
}
