# text-embedding-3-small, deployed in the quick start's Foundry account and published through the gateway. The
# gateway's Foundry User role on the account already covers the new deployment.
resource "azurerm_cognitive_deployment" "embeddings" {
  name                 = "text-embedding-3-small"
  cognitive_account_id = module.base.foundry_id

  sku {
    name     = "GlobalStandard"
    capacity = 20
  }

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }
}

# The deployment as a backend model under the quick start's provider, with a per-caller token limit. An embedding
# model supports only the embeddings endpoint, so chat calls to it fail with unsupported_endpoint.
resource "azapi_resource" "embeddings_model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.embeddings.name
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = azurerm_cognitive_deployment.embeddings.name
      description = "Foundry embedding deployment ${azurerm_cognitive_deployment.embeddings.name} published through AI Gateway."
      supportedEndpoints = [
        "/openai/v1/embeddings",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.embeddings.id
        modelName    = azurerm_cognitive_deployment.embeddings.model[0].name
        modelVersion = azurerm_cognitive_deployment.embeddings.model[0].version
      }
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = var.embeddings_tokens_per_minute
          counterKey = ["identity"]
        },
      ]
    }
  }

  schema_validation_enabled = false
}

# The alias that apps send in the request "model" field, with the same name as the deployment.
resource "azapi_resource" "embeddings_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = azapi_resource.embeddings_model.name
  parent_id = module.base.workspace_id

  body = {
    properties = {
      description = "Embeddings for search and RAG"
      backendModels = [
        { resourceId = azapi_resource.embeddings_model.id },
      ]
    }
  }

  schema_validation_enabled = false
}
