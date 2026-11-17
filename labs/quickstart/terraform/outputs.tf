output "azure_resource_group" {
  value = azurerm_resource_group.rg.name
}

output "ai_gateway_name" {
  value = module.resources.gateway_name
}

output "ai_gateway_id" {
  value = module.resources.gateway_id
}

output "ai_gateway_url" {
  value = module.resources.gateway_url
}

output "ai_gateway_model" {
  value = module.resources.alias_name
}

output "foundry_account_name" {
  value = module.resources.foundry_name
}
