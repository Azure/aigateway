# An Azure AI Gateway (Microsoft.ApiManagement/aigateways) with a system-assigned managed identity. It omits sku,
# so the resource provider applies its default (Standard). AI Gateway resources have no Terraform schema yet, so
# azapi sends the body as is. Lab 01 calls this module, and other labs reuse it.
terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
  }
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
