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
  value = azapi_resource.copilot_model.name
}

output "ai_gateway_model" {
  value = azapi_resource.copilot_alias.name
}

output "ai_gateway_key_name" {
  value = azapi_resource.copilot_key.name
}

output "ai_gateway_model_endpoint" {
  value = "${module.base.gateway_url}/default/models/openai/v1"
}

output "ai_gateway_mcp_url" {
  value = "${module.base.gateway_url}/default/toolservers/${azapi_resource.learn.name}/mcp"
}

output "foundry_account_name" {
  value = module.base.foundry_name
}
