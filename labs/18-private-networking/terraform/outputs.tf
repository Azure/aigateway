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

output "ai_gateway_key_name" {
  value = azapi_resource.api_key.name
}

output "ai_gateway_subnet_id" {
  value = azurerm_subnet.integration.id
}

output "foundry_account_name" {
  value = azurerm_cognitive_account.foundry.name
}

output "foundry_account_id" {
  value = azurerm_cognitive_account.foundry.id
}

output "foundry_endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_private_endpoint_name" {
  value = azurerm_private_endpoint.foundry.name
}

output "ai_gateway_private_endpoint_name" {
  value = var.gateway_private_endpoint ? azurerm_private_endpoint.gateway[0].name : ""
}

output "ai_gateway_private_dns_zone" {
  value = var.gateway_private_endpoint ? azurerm_private_dns_zone.gateway[0].name : ""
}

output "client_subnet_id" {
  value = var.gateway_private_endpoint ? azurerm_subnet.clients[0].id : ""
}
