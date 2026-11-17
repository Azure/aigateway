# The destination for the gateway's telemetry, like monitoring.bicep with enableOtlpIngestion: a Log Analytics
# workspace and a workspace-based Application Insights component with OTLP ingestion on. Azure then creates a managed
# resource group, ai_<component>_<id>_managed, with the Data Collection Rule and the Azure Monitor workspace for the
# metrics, and the component reports its OTLP endpoints a few minutes later. Labs 13 and 14 reuse this module.
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
  name                            = substr("${var.gateway_name}-logs", 0, 63)
  location                        = var.location
  resource_group_name             = var.resource_group_name
  sku                             = "PerGB2018"
  retention_in_days               = 30
  allow_resource_only_permissions = true
  tags                            = var.tags
}

# azurerm_application_insights can't turn on OTLP ingestion, so azapi sends AzureMonitorWorkspaceIngestionMode as is.
resource "azapi_resource" "insights" {
  type      = "Microsoft.Insights/components@2020-02-02"
  name      = "${var.gateway_name}-insights"
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

# Like connect-telemetry.sh: register Microsoft.Monitor, which the managed Azure Monitor workspace needs, then wait
# up to 15 minutes for the three OTLP endpoints and the Data Collection Rule. Terraform runs it once, with the Azure
# CLI, after it creates the component.
resource "terraform_data" "otlp_endpoints" {
  triggers_replace = [azapi_resource.insights.id]

  provisioner "local-exec" {
    command = "az provider register --namespace Microsoft.Monitor --wait && az resource wait --ids ${azapi_resource.insights.id} --api-version 2020-02-02 --custom \"properties.OTLPMetricsEndpoint && properties.OTLPLogsEndpoint && properties.OTLPTracesEndpoint && properties.DataCollectionRuleResourceId\" --interval 10 --timeout 900"
  }
}

# Then read the endpoints and the rule from the component once, with a GET that keeps its result in the state. A
# data source would read them again each time the gateway or the component changes, and replace the role assignment.
resource "azapi_resource_action" "otlp" {
  type        = "Microsoft.Insights/components@2020-02-02"
  resource_id = azapi_resource.insights.id
  method      = "GET"

  response_export_values = {
    metrics_endpoint = "properties.OTLPMetricsEndpoint"
    logs_endpoint    = "properties.OTLPLogsEndpoint"
    traces_endpoint  = "properties.OTLPTracesEndpoint"
    dcr_id           = "properties.DataCollectionRuleResourceId"
  }

  depends_on = [terraform_data.otlp_endpoints]

  lifecycle {
    replace_triggered_by = [terraform_data.otlp_endpoints]

    postcondition {
      condition     = alltrue([for k in ["metrics_endpoint", "logs_endpoint", "traces_endpoint", "dcr_id"] : try(length(self.output[k]) > 0, false)])
      error_message = "The component has no OTLP endpoints yet. Wait a few minutes, then run terraform apply -replace=module.telemetry.azapi_resource_action.otlp."
    }
  }
}
