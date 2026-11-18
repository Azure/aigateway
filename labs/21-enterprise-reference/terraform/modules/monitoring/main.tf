# Monitoring, like modules/monitoring.bicep: a Log Analytics workspace that stores the gateway's telemetry, and an
# Application Insights component on it with OTLP ingestion on. azurerm has no setting for OTLP ingestion yet, so the
# component goes through azapi.
terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

resource "azurerm_log_analytics_workspace" "logs" {
  name                = var.workspace_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days
}

resource "azapi_resource" "app_insights" {
  type      = "Microsoft.Insights/components@2020-02-02"
  name      = var.app_insights_name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = var.tags

  body = {
    kind = "web"
    properties = {
      Application_Type                   = "web"
      WorkspaceResourceId                = azurerm_log_analytics_workspace.logs.id
      AzureMonitorWorkspaceIngestionMode = "Enabled"
    }
  }

  schema_validation_enabled = false
}
