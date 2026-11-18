# Publishes the Claude deployments for Claude Code: a Foundry provider named after the account, one Anthropic
# Messages model per deployment, the alias "<account>/<deployment>" for each one with a token limit per caller, a
# cost limit per caller on budget_model's alias, and a runtime API key. The aliases have the same names as the ones
# that the portal's import creates, so the Claude Code settings work with every track. The key is never an output.
locals {
  models = { for m in var.claude_models : m.name => m }

  budget_policy = {
    type       = "costLimit"
    id         = var.budget_id
    amount     = var.budget_amount
    period     = var.budget_period
    counterKey = ["identity"]
  }
}

# The provider signs in to Foundry with the gateway's managed identity, so callers never see a Foundry credential.
resource "azapi_resource" "provider" {
  count = var.create_provider ? 1 : 0

  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = local.foundry_account_name
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Foundry"
      displayName       = local.foundry_account_name
      foundry = {
        endpoint = {
          url = "${trimsuffix(data.azapi_resource.foundry.output.properties.endpoint, "/")}/"
        }
        resourceIds = [var.foundry_account_id]
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

# Claude deployments speak the Anthropic Messages API. A Foundry account serves them on /anthropic/v1/messages, so
# the models declare that path: with /v1/messages, every call fails with "Resource not found". The models go under
# the provider, whether Terraform created it or the gateway already had it.
resource "azapi_resource" "model" {
  for_each = local.models

  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = each.key
  parent_id = "${local.workspace_id}/modelProviders/${local.foundry_account_name}"

  body = {
    properties = {
      displayName        = each.key
      supportedEndpoints = ["/anthropic/v1/messages"]
      deployment = {
        resourceId   = data.azapi_resource.deployment[each.key].id
        modelName    = data.azapi_resource.deployment[each.key].output.properties.model.name
        modelVersion = data.azapi_resource.deployment[each.key].output.properties.model.version
      }
    }
  }

  schema_validation_enabled = false
  depends_on                = [azurerm_role_assignment.foundry_user, azapi_resource.provider]
}

# Each caller identity, a key or a Microsoft Entra identity, gets its own counters. The callable name goes in
# aliasName and contains "/". The resource name can't, so it uses "-" instead.
resource "azapi_resource" "alias" {
  for_each = local.models

  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "${local.foundry_account_name}-${each.key}"
  parent_id = local.workspace_id

  body = {
    properties = {
      aliasName = "${local.foundry_account_name}/${each.key}"
      backendModels = [
        { resourceId = azapi_resource.model[each.key].id }
      ]
      policies = concat([
        {
          type       = "tokenLimit"
          count      = each.value.tokens_per_minute
          period     = "minute"
          counterKey = ["identity"]
        }
      ], each.key == var.budget_model ? [local.budget_policy] : [])
    }
  }

  schema_validation_enabled = false
}

# The runtime API key for Claude Code. Read its value with az aigateway api-key list-secrets.
resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = var.api_key_name
  parent_id = data.azapi_resource.gateway.id

  body = {
    properties = {
      displayName = var.api_key_name
    }
  }

  schema_validation_enabled = false
}
