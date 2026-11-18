# Registers the demo MCP backend as the obo-demo MCP server. Its endpoint signs in with Microsoft Entra ID
# on-behalf-of: for each call, the gateway exchanges the caller's token for a token to the backend's API, issued to
# the same user. It signs in as the token exchange app with the gateway identity. Then it assigns AI Gateway Tools
# User on the server to you, so you can call the tools.
locals {
  tools_user_role_id = "dce03f8d-857f-4e40-a90d-67770fa6ecd2"
  principal_id       = var.principal_id != "" ? var.principal_id : data.azapi_client_config.current.object_id
  gateway_url        = "https://${azapi_resource.gateway.output.properties.frontend.defaultHostname}"
}

resource "azapi_resource" "tool_server" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = "obo-demo"
  parent_id = "${azapi_resource.gateway.id}/workspaces/default"

  body = {
    properties = {
      displayName    = "OBO demo"
      description    = "Demo MCP server on Azure Container Apps, called as the signed-in user with Microsoft Entra ID on-behalf-of."
      toolServerType = "mcp"
      accessState    = "active"
      # Microsoft 365 Copilot proposes 2025-11-25.
      versions  = ["2025-11-25", "2025-06-18", "2025-03-26"]
      allowList = ["*"]
      endpoints = [
        {
          namespace = "demo"
          kind      = "mcp"
          mode      = "failClosed"
          mcp = {
            endpoint  = { url = local.backend_url }
            transport = "streamableHttp"
          }
          authentication = {
            oauth2 = {
              grantType = "tokenExchange"
              tokenExchange = {
                profile = "entraOnBehalfOf"
                federatedClientApplication = {
                  applicationId = azuread_application.token_exchange.client_id
                  appCredential = {
                    type = "userAssignedManagedIdentity"
                    # The client ID, not the principal ID.
                    clientId = azurerm_user_assigned_identity.gateway.client_id
                  }
                }
                # A scope of the backend's API. The gateway rejects /.default.
                scopes = [local.backend_scope]
              }
            }
          }
        },
      ]
    }
  }

  schema_validation_enabled = false

  depends_on = [
    azuread_application_identifier_uri.token_exchange,
    azuread_application_federated_identity_credential.gateway,
    azapi_resource.mcp_auth,
  ]
}

resource "azurerm_role_assignment" "tools_user" {
  name               = uuidv5("url", "${azapi_resource.tool_server.id}/${local.principal_id}/${local.tools_user_role_id}")
  scope              = azapi_resource.tool_server.id
  role_definition_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.tools_user_role_id}"
  principal_id       = local.principal_id
  principal_type     = "User"
}
