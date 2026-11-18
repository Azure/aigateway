# The chat alias, which routes across gpt-5-mini and the research model with CEL expressions. The gpt-5-mini backend
# model comes from the quick start's module and is only referenced, so its policies stay untouched.
locals {
  general_model = module.base.model_name
  research      = azapi_resource.research_model.name

  routing = {
    # Conditions: the research model is preferred (priority 0) but only included when its condition is true, so
    # every other request falls through to gpt-5-mini at priority 1.
    conditions = {
      description = "Sends x-workload: research requests to ${local.research}, everything else to ${local.general_model}."
      backendModels = [
        { resourceId = azapi_resource.research_model.id, priority = 0, weight = 1, when = var.research_condition },
        { resourceId = module.base.model_id, priority = 1, weight = 1 },
      ]
      selectionOrder = ["priority"]
    }

    # Affinity: both models share priority 0, and the session key picks the backend before priority and weight do.
    affinity = {
      description = "Splits sessions between ${local.general_model} and ${local.research}, and keeps each session on one of them."
      backendModels = [
        { resourceId = module.base.model_id, priority = 0, weight = 1 },
        { resourceId = azapi_resource.research_model.id, priority = 0, weight = 1 },
      ]
      selectionOrder           = ["sessionBackendPreference", "priority"]
      sessionBackendPreference = { key = var.session_key }
    }
  }
}

resource "azapi_resource" "chat_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "chat"
  parent_id = module.base.workspace_id

  body = {
    properties = local.routing[var.routing_mode]
  }

  schema_validation_enabled = false
}
