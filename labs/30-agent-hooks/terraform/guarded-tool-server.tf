# Declares the learn MCP server of lab 04 with an agent hooks policy: before each tool call and after each tool
# result, the gateway sends the call to the decision service and follows its allow or deny decision. The gateway signs
# in to the decision service with its system-assigned managed identity. The file also creates a runtime API key,
# which is never an output. Terraform sends a PUT, which replaces the whole MCP server, so keep this file as its only
# source of truth.
locals {
  hook_url = "https://${azapi_resource.hook_app.output.properties.defaultHostName}/api/tool-hook"
}

resource "azapi_resource" "tool_server" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "learn"
  parent_id = "${module.gateway.gateway_id}/workspaces/default"

  body = {
    properties = {
      toolServerType = "mcp"
      displayName    = "Microsoft Learn"
      description    = "Search and fetch official Microsoft documentation and code samples."
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
      policies = [
        {
          id             = "tool-guard"
          type           = "agentHooks"
          scope          = "resource"
          mode           = var.hook_mode
          endpoint       = { url = local.hook_url }
          authentication = { managedIdentity = { resource = local.hook_audience } }
          # Literal, non-secret headers. The gateway sends them with every hook request, and GET returns them.
          headers = [{ name = "x-hook-policy", value = "lab30" }]
          # Both points inherit the endpoint, mode, authentication, and headers above. A point can override them.
          hooks = {
            preToolCall  = {}
            postToolCall = {}
          }
        }
      ]
    }
  }

  schema_validation_enabled = false
}

# A runtime API key for the test calls. Read its value with az aigateway api-key list-secrets.
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
