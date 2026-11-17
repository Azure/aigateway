output "azure_resource_group" {
  value = var.resource_group_name
}

output "ai_gateway_name" {
  value = data.azapi_resource.gateway.name
}

output "ai_gateway_id" {
  value = data.azapi_resource.gateway.id
}

output "ai_gateway_url" {
  value = local.gateway_url
}

# Claude Code's ANTHROPIC_BASE_URL: the gateway's Anthropic route.
output "anthropic_base_url" {
  value = "${local.gateway_url}/default/models/anthropic"
}

output "provider_name" {
  value = local.foundry_account_name
}

output "alias_names" {
  value = [for m in var.claude_models : azapi_resource.alias[m.name].body.properties.aliasName]
}

output "api_key_name" {
  value = azapi_resource.api_key.name
}

output "role_assignment_id" {
  value = var.grant_foundry_user ? azurerm_role_assignment.foundry_user[0].id : ""
}

output "mcp_endpoint" {
  value = var.learn_mcp_server ? "${local.gateway_url}/default/toolservers/${azapi_resource.learn[0].name}/mcp" : ""
}
