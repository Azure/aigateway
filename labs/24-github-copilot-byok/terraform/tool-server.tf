# Registers the public Microsoft Learn MCP server as the federated MCP server learn, as lab 04 does. Clients call
# <gateway-url>/default/toolservers/learn/mcp, and the gateway publishes the backend's tools as learn_<tool>. The
# backend is required (mode failClosed), and the public server needs no credentials.
resource "azapi_resource" "learn" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "learn"
  parent_id = module.base.workspace_id

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
        },
      ]
    }
  }

  schema_validation_enabled = false
}
