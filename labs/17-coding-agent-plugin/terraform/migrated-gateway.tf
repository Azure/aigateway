# What the settled plan maps, written as Terraform:
# - the plan's prerequisite prereq:foundry-rbac: the source's identity can't carry over, so the new one gets the
#   Foundry User role on the source's Foundry account
# - the backend foundry-ai-endpoint as a Foundry model provider, on the account's root endpoint (not APIM's /openai
#   backend URL), signing in with the gateway's identity
# - the deployment as a model, with the llm-token-limit policy as a per-caller tokenLimit
# - an alias with the model's name, so apps keep sending "model": "gpt-5-mini" (decision use-model-names)
# - the learn-mcp MCP API as a federated MCP server with the namespace learn-mcp
# - one runtime key for the ticket-app subscription (decision gateway-key-per-consumer)
# What stays out, as decided: the image generation operation stays on APIM (split), the x-caller-app header has no
# equivalent (accept), and telemetry uses the gateway's built-in metrics (gateway-metrics-only).
locals {
  workspace_id         = "${module.gateway.gateway_id}/workspaces/default"
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  foundry_id_parts     = split("/", var.foundry_account_id)
}

# The account's endpoint never changes, so reading it on every plan shows no drift.
data "azurerm_cognitive_account" "foundry" {
  name                = local.foundry_id_parts[8]
  resource_group_name = local.foundry_id_parts[4]
}

resource "azurerm_role_assignment" "foundry_user" {
  name                             = uuidv5("url", "${var.foundry_account_id}/${module.gateway.gateway_id}/${local.foundry_user_role_id}")
  scope                            = var.foundry_account_id
  role_definition_id               = "/subscriptions/${local.foundry_id_parts[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = module.gateway.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = "foundry-ai-endpoint"
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Foundry"
      displayName       = "foundry-ai-endpoint"
      description       = "Migrated from the API Management backend foundry-ai-endpoint."
      foundry = {
        endpoint = {
          url = "${trimsuffix(data.azurerm_cognitive_account.foundry.endpoint, "/")}/"
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

resource "azapi_resource" "model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = var.deployment_name
  parent_id = azapi_resource.provider.id

  body = {
    properties = {
      displayName = var.deployment_name
      description = "Migrated from the API Management model API azure-openai."
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
      ]
      deployment = {
        resourceId   = "${var.foundry_account_id}/deployments/${var.deployment_name}"
        modelName    = var.deployment_name
        modelVersion = var.model_version
      }
      # llm-token-limit counted per APIM subscription. The gateway counts per caller identity: each key is one.
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = var.tokens_per_minute
          counterKey = ["identity"]
        }
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = azapi_resource.model.name
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

resource "azapi_resource" "tool_server" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "learn-mcp"
  parent_id = local.workspace_id

  body = {
    properties = {
      displayName    = "learn-mcp"
      description    = "Migrated from the API Management MCP server learn-mcp."
      toolServerType = "mcp"
      endpoints = [
        {
          namespace = "learn-mcp"
          kind      = "mcp"
          mode      = "failClosed"
          mcp = {
            endpoint = {
              url = "https://learn.microsoft.com/api/mcp"
            }
            transport = "streamableHttp"
          }
        }
      ]
    }
  }

  schema_validation_enabled = false
}

# One key for each APIM subscription. Key values never carry over: the gateway generates new ones.
resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = "ticket-app"
  parent_id = module.gateway.gateway_id

  body = {
    properties = {
      displayName = "Ticket app"
    }
  }

  schema_validation_enabled = false
}
