# Tools, like modules/tools.bicep: the Microsoft Learn MCP server behind the gateway, and the AI Gateway Tools User
# role on it for Microsoft Entra principals.
terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

locals {
  tools_user_role_id = "dce03f8d-857f-4e40-a90d-67770fa6ecd2"
}

resource "azapi_resource" "tool_server" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01"
  name      = var.server_name
  parent_id = "${var.gateway_id}/workspaces/default"

  body = {
    properties = {
      displayName    = var.display_name
      description    = var.server_description
      toolServerType = "mcp"
      endpoints = [
        {
          namespace = var.namespace
          kind      = "mcp"
          mcp = {
            endpoint = {
              url = var.mcp_url
            }
            transport = "streamableHttp"
          }
        },
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azurerm_role_assignment" "tool_users" {
  for_each                         = { for user in var.tool_users : user.principal_id => user }
  name                             = uuidv5("url", "${azapi_resource.tool_server.id}/${each.key}/${local.tools_user_role_id}")
  scope                            = azapi_resource.tool_server.id
  role_definition_id               = "/subscriptions/${split("/", var.gateway_id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.tools_user_role_id}"
  principal_id                     = each.key
  principal_type                   = each.value.principal_type
  skip_service_principal_aad_check = each.value.principal_type == "ServicePrincipal"
}
