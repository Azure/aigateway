# Publishes the Foundry deployment through the gateway: a Foundry model provider that signs in with the gateway's
# managed identity, the deployment as a backend model with a per-caller token limit, an alias that apps send in
# the "model" field, and a runtime API key for the first app. Read the key with az aigateway api-key list-secrets.
locals {
  workspace_id = "${module.gateway.gateway_id}/workspaces/default"
}

resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = "foundry-models"
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Foundry"
      displayName       = "Foundry models"
      description       = "Managed-identity Foundry provider created by the first-model-call lab."
      foundry = {
        endpoint = {
          url = "${trimsuffix(azurerm_cognitive_account.foundry.endpoint, "/")}/"
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

resource "azapi_resource" "model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.model.name
  parent_id = azapi_resource.provider.id

  body = {
    properties = {
      displayName = azurerm_cognitive_deployment.model.name
      description = "Foundry deployment ${azurerm_cognitive_deployment.model.name} published through AI Gateway."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId = azurerm_cognitive_deployment.model.id
        modelName  = azurerm_cognitive_deployment.model.name
      }
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = var.tokens_per_minute
          counterKey = ["identity"]
        }
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = azapi_resource.model.name
  parent_id = local.workspace_id

  body = {
    properties = {
      backendModels = [
        { resourceId = azapi_resource.model.id }
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = "app-first-call"
  parent_id = module.gateway.gateway_id

  body = {
    properties = {
      displayName = "First call app key"
    }
  }

  schema_validation_enabled = false
}
