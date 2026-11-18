# Lab 33 with Terraform: creates the resource group rg-<environment_name>, two user-assigned managed identities, a
# gateway that lists both of its identities, the three Microsoft Entra ID applications of the on-behalf-of chain
# (entra.tf), the demo MCP server on Azure Container Apps (mcp-server.tf), then the obo-demo MCP server with an
# on-behalf-of endpoint and AI Gateway Tools User on it for you (tool-server.tf).
#
# Lab 01's module declares the gateway with only its system-assigned identity, and the gateway keeps only the
# identities that its identity block lists. So, like lab 12, this lab declares the gateway itself.
data "azapi_client_config" "current" {}

locals {
  suffix    = substr(sha1("${data.azapi_client_config.current.subscription_id}/${var.environment_name}/${var.location}"), 0, 6)
  tags      = { "environment-name" = var.environment_name }
  base_name = "aigw-lab33-${local.suffix}"
  tenant_id = data.azapi_client_config.current.tenant_id
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.environment_name}"
  location = var.location
  tags     = local.tags
}

# The gateway signs in as the token exchange app with this identity.
resource "azurerm_user_assigned_identity" "gateway" {
  name                = "id-${local.base_name}-gateway"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
}

# The container app pulls its image with this identity.
resource "azurerm_user_assigned_identity" "mcp" {
  name                = "id-${local.base_name}-mcp"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
}

# The gateway, with its system-assigned identity and the gateway identity. It omits sku, so it gets the default SKU.
resource "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/aigateways@2026-11-01"
  name      = "aigw-${local.suffix}"
  parent_id = azurerm_resource_group.rg.id
  location  = var.location
  tags      = local.tags

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.gateway.id]
  }

  body = {
    properties = {}
  }

  schema_validation_enabled = false
  response_export_values    = ["properties.frontend.defaultHostname"]

  # Activation can take longer than azapi's default 30 minutes in some regions.
  timeouts {
    create = "60m"
  }
}
