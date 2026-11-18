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

output "mcp_server" {
  value = azapi_resource.tool_server.name
}

output "mcp_endpoint" {
  value = "${module.gateway.gateway_url}/default/toolservers/${azapi_resource.tool_server.name}/mcp"
}

output "hook_app_name" {
  value = azapi_resource.hook_app.name
}

output "hook_url" {
  value = local.hook_url
}

output "hook_client_id" {
  value = azuread_application.hook.client_id
}

output "hook_object_id" {
  value = azuread_application.hook.object_id
}

output "hook_audience" {
  value = local.hook_audience
}

output "hook_log_workspace_id" {
  value = azurerm_log_analytics_workspace.hook.workspace_id
}
