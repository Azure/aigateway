# Registers both deployments as backend models under the quick start's Foundry provider, then publishes the
# chat-failover alias: the primary at priority 0, the backup at priority 1. With failover = "on", one failure rule
# switches a request to the backup when a backend returns 429. Rules use CEL over the backend response.
locals {
  # A 429 from a backend switches the request to the next backend model at once (no same-backend retries), and keeps
  # the throttled backend out of the alias for exclude_for.
  throttling_rule = merge(
    { when = "@cel(response != null && response.status_code == 429)" },
    var.exclude_for == "" ? {} : { excludeFor = var.exclude_for },
  )
}

# The gateway calls the Foundry deployment that deployment.modelName names, so it matches the deployment name.
resource "azapi_resource" "primary" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.primary.name
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = azurerm_cognitive_deployment.primary.name
      description = "Primary deployment of the chat-failover alias."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.primary.id
        modelName    = azurerm_cognitive_deployment.primary.name
        modelVersion = local.primary_model_version
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "backup" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = azurerm_cognitive_deployment.backup.name
  parent_id = module.base.provider_id

  body = {
    properties = {
      displayName = azurerm_cognitive_deployment.backup.name
      description = "Backup deployment of the chat-failover alias."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = azurerm_cognitive_deployment.backup.id
        modelName    = azurerm_cognitive_deployment.backup.name
        modelVersion = var.backup_model_version
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "chat-failover"
  parent_id = module.base.workspace_id

  body = {
    properties = {
      description = (var.failover == "on"
        ? "Prefers ${azapi_resource.primary.name}, and fails over to ${azapi_resource.backup.name} on 429."
      : "Prefers ${azapi_resource.primary.name}. ${azapi_resource.backup.name} has a lower preference.")
      backendModels = [
        {
          resourceId = azapi_resource.primary.id
          priority   = 0
          weight     = 1
        },
        {
          resourceId = azapi_resource.backup.id
          priority   = 1
          weight     = 1
        },
      ]
      selectionOrder = ["priority"]
      # Up to 3 extra sends per request. Without the rule, the API default, 0, applies.
      maxRetryAttempts = var.failover == "on" ? 3 : null
      failures         = var.failover == "on" ? [local.throttling_rule] : null
    }
  }

  # With failover = "off", leave maxRetryAttempts and failures out of the request rather than sending null.
  ignore_null_property      = true
  schema_validation_enabled = false
}
