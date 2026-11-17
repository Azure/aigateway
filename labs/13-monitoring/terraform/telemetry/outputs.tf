output "app_insights_id" {
  value = azapi_resource.insights.id
}

output "app_insights_name" {
  value = azapi_resource.insights.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.logs.id
}

output "log_analytics_workspace_name" {
  value = azurerm_log_analytics_workspace.logs.name
}

output "log_analytics_customer_id" {
  value = azurerm_log_analytics_workspace.logs.workspace_id
}

output "data_collection_rule_id" {
  value = local.dcr_id
}

output "telemetry_exporter_id" {
  value = azapi_resource.exporter.id
}

output "telemetry_exporter_name" {
  value = azapi_resource.exporter.name
}
