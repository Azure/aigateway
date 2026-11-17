# Registers the public Microsoft Learn MCP server as the federated MCP server learn. Clients call one governed
# endpoint, <gateway-url>/default/toolservers/learn/mcp, and the gateway publishes each backend's tools with a
# namespace prefix (<namespace>_<tool>). A required backend has mode failClosed: tool discovery fails if it fails.
# An optional one, such as the second_namespace backend, has mode failOpen: the gateway skips it.
locals {
  learn_url = "https://learn.microsoft.com/api/mcp"

  primary_endpoint = {
    namespace = "learn"
    kind      = "mcp"
    mode      = "failClosed"
    mcp = {
      endpoint  = { url = local.learn_url }
      transport = "streamableHttp"
    }
  }

  second_endpoint = {
    namespace = var.second_namespace
    kind      = "mcp"
    mode      = "failOpen"
    mcp = {
      endpoint  = { url = local.learn_url }
      transport = "streamableHttp"
    }
  }

  # An empty list keeps the server's current versions, or the legacy defaults on a new server.
  versions = length(var.supported_versions) == 0 ? {} : { versions = var.supported_versions }
}

resource "azapi_resource" "tool_server" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "learn"
  parent_id = "${module.gateway.gateway_id}/workspaces/default"

  body = {
    properties = merge({
      displayName    = "Microsoft Learn"
      description    = "Search and fetch official Microsoft documentation and code samples."
      toolServerType = "mcp"
      endpoints      = var.second_namespace == "" ? [local.primary_endpoint] : [local.primary_endpoint, local.second_endpoint]
    }, local.versions)
  }

  schema_validation_enabled = false
}

# A runtime API key for the MCP clients. Read its value with az aigateway api-key list-secrets.
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
