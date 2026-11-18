output "azure_resource_group" {
  value = azurerm_resource_group.rg.name
}

output "ai_gateway_name" {
  value = module.gateway.gateway_name
}

output "ai_gateway_id" {
  value = module.gateway.gateway_id
}

output "ai_gateway_url" {
  value = module.gateway.gateway_url
}

output "ai_gateway_provider" {
  value = azapi_resource.provider.name
}

output "ai_gateway_backend_model" {
  value = azapi_resource.model.name
}

output "ai_gateway_model" {
  value = azapi_resource.alias.name
}

output "ai_gateway_api_key_name" {
  value = azapi_resource.api_key.name
}

output "foundry_account_name" {
  value = azurerm_cognitive_account.foundry.name
}
