output "gateway_name" {
  value = azapi_resource.gateway.name
}

output "gateway_id" {
  value = azapi_resource.gateway.id
}

output "gateway_url" {
  # try() keeps terraform import working: an imported resource has no output until the next refresh.
  value = "https://${try(azapi_resource.gateway.output.properties.frontend.defaultHostname, "")}"
}

output "alias_name" {
  value = azapi_resource.alias.name
}

output "foundry_name" {
  value = azurerm_cognitive_account.foundry.name
}

# For the labs that build on this module: they call it, then add their own resources.
output "gateway_principal_id" {
  value = azapi_resource.gateway.identity[0].principal_id
}

output "workspace_id" {
  value = "${azapi_resource.gateway.id}/workspaces/default"
}

output "provider_name" {
  value = azapi_resource.provider.name
}

output "provider_id" {
  value = azapi_resource.provider.id
}

output "model_name" {
  value = azapi_resource.model.name
}

output "model_id" {
  value = azapi_resource.model.id
}

output "foundry_id" {
  value = azurerm_cognitive_account.foundry.id
}

output "foundry_endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

output "deployment_id" {
  value = azurerm_cognitive_deployment.model.id
}

output "api_key_name" {
  value = azapi_resource.api_key.name
}
