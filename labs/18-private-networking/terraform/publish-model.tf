# Lab 02's publishing steps for the lab's Foundry deployment: the Foundry User role for the gateway's managed
# identity, the foundry-private model provider, the gpt-5-mini backend model with a token limit, the private-chat
# alias that apps send in the "model" field, and the runtime API key private-net-lab. Read the key's value with
# az aigateway api-key list-secrets; it's never an output, so it stays out of the Terraform state.
locals {
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  workspace_id         = "${module.gateway.gateway_id}/workspaces/default"
}

# The gateway calls Foundry with its own identity, so it needs the Foundry User role on the account.
resource "azurerm_role_assignment" "foundry_user" {
  name                             = uuidv5("url", "${azurerm_cognitive_account.foundry.id}/${module.gateway.gateway_id}/${local.foundry_user_role_id}")
  scope                            = azurerm_cognitive_account.foundry.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = module.gateway.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = "foundry-private"
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
        resourceId   = azurerm_cognitive_deployment.model.id
        modelName    = azurerm_cognitive_deployment.model.name
        modelVersion = "2025-08-07"
      }
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = 10000
          counterKey = ["identity"]
        }
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "private-chat"
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
  name      = "private-net-lab"
  parent_id = module.gateway.gateway_id

  body = {
    properties = {
      displayName = "private-net-lab"
    }
  }

  schema_validation_enabled = false
}
