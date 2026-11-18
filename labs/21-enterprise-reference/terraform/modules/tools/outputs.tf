output "tool_server_name" {
  value = azapi_resource.tool_server.name
}

output "tool_server_id" {
  value = azapi_resource.tool_server.id
}

output "mcp_endpoint" {
  value = "https://${var.gateway_hostname}/default/toolservers/${azapi_resource.tool_server.name}/mcp"
}
