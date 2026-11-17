# The higher-quality model, deployed in the quick start's Foundry account next to gpt-5-mini and registered as a
# second backend model under the quick start's provider. The gateway's Foundry User role on the account already
# covers it. The portal's Foundry import names gpt-5.5 as gpt-5-5, so every track of the lab uses that name.
resource "azurerm_cognitive_deployment" "large" {
  name                 = var.large_model_name
  cognitive_account_id = module.base.foundry_id

  sku {
    name     = "GlobalStandard"
    capacity = 20
  }

  model {
    format  = "OpenAI"
    name    = var.large_model_name
    version = var.large_model_version
  }
}

resource "azapi_resource" "large_model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = replace(var.large_model_name, ".", "-")
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = var.large_model_name
      description = "Higher-quality model that the auto alias can select."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.large.id
        modelName    = var.large_model_name
        modelVersion = var.large_model_version
      }
    }
  }

  schema_validation_enabled = false
}
