output "azure_resource_group" {
  value = azurerm_resource_group.rg.name
}

output "ai_gateway_name" {
  value = module.base.gateway_name
}

output "ai_gateway_id" {
  value = module.base.gateway_id
}

output "ai_gateway_url" {
  value = module.base.gateway_url
}

output "ai_gateway_provider" {
  value = module.base.provider_name
}

output "ai_gateway_backend_model" {
  value = module.base.model_name
}

output "ai_gateway_model" {
  value = module.base.alias_name
}

output "foundry_account_name" {
  value = module.base.foundry_name
}

# Names only: read the values with az aigateway api-key list-secrets.
output "ai_gateway_api_key_names" {
  value = [for name in var.api_key_names : azapi_resource.api_keys[name].name]
}
