# Declares the learn MCP server of lab 04, with its learn and docs backends, plus lab 05's tool controls: the tools
# it publishes (allowList), the tools it refuses to run (blockList), whether clients can reach it (accessState), and
# a request rate limit for each caller. An apply sends a PUT, which replaces the whole MCP server, so keep this
# configuration as its only source of truth.
locals {
  learn_url = "https://learn.microsoft.com/api/mcp"

  rate_limit = {
    type       = "requestRateLimit"
    count      = var.calls_per_period
    period     = "PT${var.period_seconds}S"
    counterKey = var.counter_key
  }
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
      accessState    = var.server_access
      allowList      = var.allowed_tools
      blockList      = var.blocked_tools
      endpoints = [
        {
          namespace = "learn"
          kind      = "mcp"
          mode      = "failClosed"
          mcp = {
            endpoint  = { url = local.learn_url }
            transport = "streamableHttp"
          }
        },
        {
          namespace = "docs"
          kind      = "mcp"
          mode      = "failOpen"
          mcp = {
            endpoint  = { url = local.learn_url }
            transport = "streamableHttp"
          }
        },
      ]
      policies = var.calls_per_period > 0 ? [local.rate_limit] : []
    }
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
