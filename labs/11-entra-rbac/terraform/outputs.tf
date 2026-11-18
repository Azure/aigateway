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

output "ai_gateway_role_assignment_id" {
  value = azurerm_role_assignment.runtime.id
}

output "ai_gateway_role_scope_id" {
  value = azurerm_role_assignment.runtime.scope
}
