output "azure_resource_group" {
  value = azurerm_resource_group.rg.name
}

output "azure_location" {
  value = azurerm_resource_group.rg.location
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

output "foundry_app_account_name" {
  value = azurerm_cognitive_account.apps.name
}

output "foundry_project_name" {
  value = azurerm_cognitive_account_project.project.name
}

output "foundry_project_endpoint" {
  value = "https://${azurerm_cognitive_account.apps.custom_subdomain_name}.services.ai.azure.com/api/projects/${azurerm_cognitive_account_project.project.name}"
}

output "foundry_connection_name" {
  value = azapi_resource.connection.name
}

output "foundry_model" {
  value = "${azapi_resource.connection.name}/${module.base.alias_name}"
}
