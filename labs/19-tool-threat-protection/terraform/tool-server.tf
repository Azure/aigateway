# The learn MCP server of lab 04 with an optional Agent 365 tool threat protection policy, which has Microsoft
# Defender and Microsoft Purview evaluate each tool request (pre_invocation), each tool result (post_invocation), or
# both. The signed-in user gets AI Gateway Tools User on the server, to call tools with a delegated token.
# Terraform sends a PUT, which replaces the whole MCP server, so keep this file as its only source of truth.
locals {
  # AI Gateway Tools User: call the tools of an MCP server with a Microsoft Entra ID token.
  tools_user_role_id = "dce03f8d-857f-4e40-a90d-67770fa6ecd2"
  principal_id       = var.principal_id != "" ? var.principal_id : data.azapi_client_config.current.object_id
}

resource "azapi_resource" "tool_server" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "learn"
  parent_id = "${module.gateway.gateway_id}/workspaces/default"

  body = {
    properties = {
      displayName    = "Microsoft Learn"
      description    = "Search and fetch official Microsoft documentation and code samples."
      toolServerType = "mcp"
      endpoints = [
        {
          namespace = "learn"
          kind      = "mcp"
          mode      = "failClosed"
          mcp = {
            endpoint  = { url = "https://learn.microsoft.com/api/mcp" }
            transport = "streamableHttp"
          }
        }
      ]
      # A tool threat protection policy needs at least one stage.
      policies = var.pre_invocation || var.post_invocation ? [
        {
          type           = "toolThreatProtection"
          preInvocation  = var.pre_invocation
          postInvocation = var.post_invocation
        }
      ] : []
    }
  }

  schema_validation_enabled = false
}

resource "azurerm_role_assignment" "tools_user" {
  name               = uuidv5("url", "${azapi_resource.tool_server.id}/${local.principal_id}/${local.tools_user_role_id}")
  scope              = azapi_resource.tool_server.id
  role_definition_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.tools_user_role_id}"
  principal_id       = local.principal_id
  principal_type     = "User"
}

# A runtime API key for the key-only test call. Read its value with az aigateway api-key list-secrets; it's never an
# output, so it stays out of the Terraform state.
resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = "app-first-call"
  parent_id = module.gateway.gateway_id

  body = {
    properties = {
      displayName = "app-first-call"
    }
  }

  schema_validation_enabled = false
}
