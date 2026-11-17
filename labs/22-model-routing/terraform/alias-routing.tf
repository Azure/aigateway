# Registers the candidate deployment under the quick start's Foundry provider, then publishes the chat alias, which
# either splits traffic between gpt-5-mini and the candidate by weight, or prefers gpt-5-mini by priority.
# gpt-5-mini is only referenced, so its settings stay untouched.
locals {
  primary   = module.base.model_name
  candidate = azapi_resource.candidate.name

  # The chat alias's backend models for each strategy. Lower priority numbers are preferred (0 to 100), and the
  # weights split the traffic among the models that share a priority (1 to 100).
  routes = {
    weighted = [
      { resourceId = module.base.model_id, priority = 0, weight = 100 - var.candidate_weight },
      { resourceId = azapi_resource.candidate.id, priority = 0, weight = var.candidate_weight },
    ]
    priority = [
      { resourceId = module.base.model_id, priority = 0, weight = 1 },
      { resourceId = azapi_resource.candidate.id, priority = 1, weight = 1 },
    ]
  }
  descriptions = {
    weighted = "Splits traffic ${100 - var.candidate_weight}/${var.candidate_weight} between ${local.primary} and ${local.candidate}."
    priority = "Prefers ${local.primary}. ${local.candidate} has a lower preference."
  }
}

resource "azapi_resource" "candidate" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.candidate.name
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = azurerm_cognitive_deployment.candidate.name
      description = "Candidate deployment that the chat alias routes to."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.candidate.id
        modelName    = var.candidate_model_name
        modelVersion = var.candidate_model_version
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "chat_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "chat"
  parent_id = module.base.workspace_id

  body = {
    properties = {
      description   = local.descriptions[var.strategy]
      backendModels = local.routes[var.strategy]
    }
  }

  schema_validation_enabled = false
}
