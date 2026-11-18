# Runtime API keys, like modules/keys.bicep: one per app, named after it. Read a key's value with
# az aigateway api-key list-secrets; no output holds it.
terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
  }
}

resource "azapi_resource" "api_key" {
  for_each  = toset(var.app_names)
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = each.value
  parent_id = var.gateway_id

  body = {
    properties = {
      displayName = "${each.value} runtime key"
    }
  }

  schema_validation_enabled = false
}
