# The research model, deployed in the quick start's Foundry account next to gpt-5-mini and registered as a second
# backend model under the quick start's provider. The gateway's Foundry User role on the account already covers it.
resource "azurerm_cognitive_deployment" "research" {
  name                 = var.research_model_name
  cognitive_account_id = module.base.foundry_id

  # 50 also allows 50 requests per minute, enough for the lab's scripts.
  sku {
    name     = "GlobalStandard"
    capacity = 50
  }

  model {
    format  = "OpenAI"
    name    = var.research_model_name
    version = var.research_model_version
  }
}

resource "azapi_resource" "research_model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.research.name
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = azurerm_cognitive_deployment.research.name
      description = "Research model that the chat alias routes to."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.research.id
        modelName    = var.research_model_name
        modelVersion = var.research_model_version
      }
    }
  }

  schema_validation_enabled = false
}
