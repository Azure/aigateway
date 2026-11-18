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

output "ai_gateway_principal_id" {
  value = module.base.gateway_principal_id
}

output "app_insights_id" {
  value = module.telemetry.app_insights_id
}

output "app_insights_name" {
  value = module.telemetry.app_insights_name
}

output "log_analytics_workspace_id" {
  value = module.telemetry.log_analytics_workspace_id
}

output "log_analytics_customer_id" {
  value = module.telemetry.log_analytics_customer_id
}

output "telemetry_exporter_name" {
  value = module.telemetry.telemetry_exporter_name
}

output "ai_gateway_role_assignment_id" {
  value = azurerm_role_assignment.models_user.id
}
