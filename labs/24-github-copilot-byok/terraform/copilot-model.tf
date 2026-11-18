# Publishes gpt-6.1-sol for GitHub Copilot: a deployment in the quick start's Foundry account, a backend model under
# the quick start's Foundry provider with a per-caller token limit, the gpt-6.1-sol alias, and the github-copilot
# runtime API key. The gateway's Foundry User role on the account already covers the new deployment.
resource "azurerm_cognitive_deployment" "copilot" {
  name                 = var.model_name
  cognitive_account_id = module.base.foundry_id

  sku {
    name     = var.model_sku
    capacity = var.model_capacity
  }

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }
}

resource "azapi_resource" "copilot_model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.copilot.name
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = var.model_name
      description = "Foundry deployment ${var.model_name} published through AI Gateway for GitHub Copilot."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.copilot.id
        modelName    = var.model_name
        modelVersion = var.model_version
      }
      # Each caller identity, here each API key, gets this many tokens per minute.
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = var.tokens_per_minute
          counterKey = ["identity"]
        },
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "copilot_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = var.model_name
  parent_id = module.base.workspace_id

  body = {
    properties = {
      backendModels = [
        { resourceId = azapi_resource.copilot_model.id },
      ]
    }
  }

  schema_validation_enabled = false
}

# The key that GitHub Copilot sends. Read its value with az aigateway api-key list-secrets.
resource "azapi_resource" "copilot_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = "github-copilot"
  parent_id = module.base.gateway_id

  body = {
    properties = {
      displayName = "GitHub Copilot"
    }
  }

  schema_validation_enabled = false
}
