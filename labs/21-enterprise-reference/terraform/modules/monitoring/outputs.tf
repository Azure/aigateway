output "workspace_id" {
  value = azurerm_log_analytics_workspace.logs.id
}

output "workspace_name" {
  value = azurerm_log_analytics_workspace.logs.name
}

output "app_insights_id" {
  value = azapi_resource.app_insights.id
}

output "app_insights_name" {
  value = azapi_resource.app_insights.name
}
