# The outputs of infra/main.bicep in snake_case, plus azure_resource_group. No output holds a key.
output "azure_resource_group" {
  value = azurerm_resource_group.gateway.name
}

output "azure_location" {
  value = var.location
}

output "azure_tenant_id" {
  value = data.azapi_client_config.current.tenant_id
}

output "ai_gateway_name" {
  value = module.gateway.name
}

output "ai_gateway_location" {
  value = local.ai_gateway_location
}

output "ai_gateway_resource_group" {
  value = azurerm_resource_group.gateway.name
}

output "ai_gateway_resource_id" {
  value = module.gateway.id
}

output "ai_gateway_url" {
  value = module.gateway.url
}

output "ai_gateway_principal_id" {
  value = module.gateway.principal_id
}

output "ai_gateway_model" {
  value = module.models.alias_name
}

output "mcp_endpoint" {
  value = module.tools.mcp_endpoint
}

output "api_key_names" {
  value = module.keys.api_key_names
}

output "foundry_models_resource_group" {
  value = azurerm_resource_group.foundry_models.name
}

output "foundry_models_name" {
  value = module.foundry.name
}

output "foundry_models_resource_id" {
  value = module.foundry.id
}

output "application_insights_name" {
  value = module.monitoring.app_insights_name
}

output "log_analytics_workspace_id" {
  value = module.monitoring.workspace_id
}
