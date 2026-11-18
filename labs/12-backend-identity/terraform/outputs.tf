output "azure_resource_group" {
  value = azurerm_resource_group.rg.name
}

output "ai_gateway_name" {
  value = azapi_resource.gateway.name
}

output "ai_gateway_id" {
  value = azapi_resource.gateway.id
}

output "ai_gateway_url" {
  # try() keeps terraform import working: an imported resource has no output until the next refresh.
  value = "https://${try(azapi_resource.gateway.output.properties.frontend.defaultHostname, "")}"
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

output "foundry_account_name" {
  value = azurerm_cognitive_account.foundry.name
}

output "foundry_id" {
  value = azurerm_cognitive_account.foundry.id
}

output "identity_name" {
  value = azurerm_user_assigned_identity.backends.name
}

output "identity_id" {
  value = azurerm_user_assigned_identity.backends.id
}

output "identity_client_id" {
  value = azurerm_user_assigned_identity.backends.client_id
}

output "identity_principal_id" {
  value = azurerm_user_assigned_identity.backends.principal_id
}

output "provider_identity" {
  value = var.use_user_assigned_identity ? azurerm_user_assigned_identity.backends.client_id : "system-assigned"
}
