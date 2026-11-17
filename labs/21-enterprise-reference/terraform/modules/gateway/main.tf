# The gateway, like modules/gateway.bicep: an Azure AI Gateway with a system-assigned managed identity, an optional
# backend subnet, and the Foundry User role on each Foundry account it calls. AI Gateway resources have no
# Terraform schema yet, so azapi sends the body as is.
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
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
}

resource "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/aigateways@2026-11-01"
  name      = var.gateway_name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = var.tags

  identity {
    type = "SystemAssigned"
  }

  # The optional backend subnet turns on outbound virtual network integration.
  body = {
    properties = var.backend_subnet_id == "" ? {} : { backend = { subnet = { id = var.backend_subnet_id } } }
  }

  schema_validation_enabled = false
  response_export_values    = ["properties.frontend.defaultHostname"]

  # Activation can take longer than azapi's default 30 minutes in some regions.
  timeouts {
    create = "60m"
  }
}

# The gateway calls Foundry with its own identity, so it needs the Foundry User role on each account.
resource "azurerm_role_assignment" "foundry_user" {
  count                            = length(var.foundry_resource_ids)
  name                             = uuidv5("url", "${var.foundry_resource_ids[count.index]}/${azapi_resource.gateway.id}/${local.foundry_user_role_id}")
  scope                            = var.foundry_resource_ids[count.index]
  role_definition_id               = "/subscriptions/${split("/", var.foundry_resource_ids[count.index])[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = azapi_resource.gateway.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
