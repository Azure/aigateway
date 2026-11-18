# Registers the public Microsoft Learn MCP server as the MCP server learn when learn_mcp_server is true, like lab
# 04's tool-server.bicep: one backend in the learn namespace, with no credentials. Claude Code calls it on
# <gateway-url>/default/toolservers/learn/mcp with the same claude-code key as the models.
resource "azapi_resource" "learn" {
  count = var.learn_mcp_server ? 1 : 0

  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "learn"
  parent_id = local.workspace_id

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
    }
  }

  schema_validation_enabled = false
}
