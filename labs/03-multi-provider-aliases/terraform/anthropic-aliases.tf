# Adds Anthropic to the gateway as a custom provider, registers two Claude models, and publishes them behind three
# callable aliases: support-chat and batch-chat, each with its own per-caller token limit, and anthropic/<smart model>.
locals {
  provider_name      = "anthropic"
  support_chat_model = var.support_chat_model == "" ? var.fast_model : var.support_chat_model

  # The callable name goes in aliasName and can contain "/". The resource name can't, so it uses "-" instead.
  aliases = {
    "support-chat" = {
      alias_name        = "support-chat"
      model             = local.support_chat_model
      tokens_per_minute = var.support_chat_tokens_per_minute
    }
    "batch-chat" = {
      alias_name        = "batch-chat"
      model             = var.fast_model
      tokens_per_minute = var.batch_chat_tokens_per_minute
    }
    "${local.provider_name}-${var.smart_model}" = {
      alias_name        = "${local.provider_name}/${var.smart_model}"
      model             = var.smart_model
      tokens_per_minute = 0
    }
  }
}

# Leave /v1 off the endpoint. Anthropic expects the raw key in x-api-key, with no "Bearer" scheme. The header goes in
# sensitive_body, which is write-only: Terraform sends it on every create and update, because reads hide its value,
# and never stores it in the state.
resource "azapi_resource" "anthropic" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = local.provider_name
  parent_id = module.base.workspace_id

  body = {
    properties = {
      modelProviderType = "Custom"
      displayName       = "Anthropic"
      description       = "Anthropic Messages API, with the key in the x-api-key header."
      custom = {
        endpoint = {
          url = "https://api.anthropic.com"
        }
      }
    }
  }

  sensitive_body = {
    properties = {
      authentication = {
        headers = [
          {
            name  = "x-api-key"
            value = var.anthropic_api_key
          }
        ]
      }
    }
  }

  schema_validation_enabled = false
}

# Custom providers list the provider path in supportedEndpoints and leave out apiFormat. Names may only contain
# lowercase letters, digits, and hyphens; modelName keeps the provider's real model ID.
resource "azapi_resource" "anthropic_model" {
  for_each = toset([var.fast_model, var.smart_model])

  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = each.key
  parent_id = azapi_resource.anthropic.id

  body = {
    properties = {
      displayName        = each.key
      supportedEndpoints = ["/v1/messages"]
      deployment = {
        modelName = each.key
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "anthropic_alias" {
  for_each = local.aliases

  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = each.key
  parent_id = module.base.workspace_id

  body = {
    properties = {
      aliasName = each.value.alias_name
      backendModels = [
        { resourceId = azapi_resource.anthropic_model[each.value.model].id }
      ]
      policies = [
        for count in(each.value.tokens_per_minute > 0 ? [each.value.tokens_per_minute] : []) : {
          type       = "tokenLimit"
          count      = count
          period     = "minute"
          counterKey = ["identity"]
        }
      ]
    }
  }

  schema_validation_enabled = false
}
