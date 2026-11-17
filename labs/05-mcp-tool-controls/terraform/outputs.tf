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

output "mcp_endpoint" {
  value = "${module.gateway.gateway_url}/default/toolservers/${azapi_resource.tool_server.name}/mcp"
}
