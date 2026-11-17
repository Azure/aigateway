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
  value = local.gateway_url
}

output "mcp_server" {
  value = azapi_resource.tool_server.name
}

output "mcp_endpoint" {
  value = "${local.gateway_url}/default/toolservers/${azapi_resource.tool_server.name}/mcp"
}

output "backend_url" {
  value = local.backend_url
}

output "backend_app_id" {
  value = azuread_application.backend.client_id
}

output "backend_scope" {
  value = local.backend_scope
}

output "token_exchange_app_id" {
  value = azuread_application.token_exchange.client_id
}

output "connector_app_id" {
  value = azuread_application.connector.client_id
}

output "gateway_identity_client_id" {
  value = azurerm_user_assigned_identity.gateway.client_id
}

output "container_app_name" {
  value = azurerm_container_app.mcp.name
}
