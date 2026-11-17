# Telemetry, like scripts/connect-telemetry.sh and modules/telemetry.bicep: reads the OTLP endpoints and the Data
# Collection Rule of the Application Insights component, grants the gateway's identity Monitoring Metrics Publisher
# on the rule, then creates the gateway's OpenTelemetry exporter with the recommended token claims.
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

locals {
  metrics_publisher_role_id = "3913510d-42f4-4e42-8a64-420c390055eb"
}

# Like connect-telemetry.sh: register Microsoft.Monitor, which the managed Azure Monitor workspace needs, then wait
# up to 10 minutes for the three OTLP endpoints and the Data Collection Rule. Terraform runs it once, with the Azure
# CLI, after it creates the component.
resource "terraform_data" "otlp_endpoints" {
  triggers_replace = [var.app_insights_id]

  provisioner "local-exec" {
    command = "az provider register --namespace Microsoft.Monitor --wait && az resource wait --ids ${var.app_insights_id} --api-version 2020-02-02 --custom \"properties.OTLPMetricsEndpoint && properties.OTLPLogsEndpoint && properties.OTLPTracesEndpoint && properties.DataCollectionRuleResourceId\" --interval 10 --timeout 600"
  }
}

# Then read the endpoints and the rule once, with a GET that keeps its result in the state. A data source would read
# them again each time the gateway changes, and replace the role assignment.
resource "azapi_resource_action" "otlp" {
  type        = "Microsoft.Insights/components@2020-02-02"
  resource_id = var.app_insights_id
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
      condition = alltrue([
        for field in ["metrics_endpoint", "logs_endpoint", "traces_endpoint", "dcr_id"] :
        try(length(self.output[field]) > 0, false)
      ])
      error_message = "Application Insights has no OTLP endpoints or Data Collection Rule yet. Wait a few minutes, then run terraform apply -replace=module.telemetry.azapi_resource_action.otlp."
    }
  }
}

# A direct role assignment works on the rule, though its managed resource group's deny assignment blocks deployments.
resource "azurerm_role_assignment" "metrics_publisher" {
  name                             = uuidv5("url", "${azapi_resource_action.otlp.output.dcr_id}/${var.gateway_id}/${local.metrics_publisher_role_id}")
  scope                            = azapi_resource_action.otlp.output.dcr_id
  role_definition_id               = "/subscriptions/${split("/", var.gateway_id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.metrics_publisher_role_id}"
  principal_id                     = var.gateway_principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azapi_resource" "exporter" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2026-11-01"
  name      = var.exporter_name
  parent_id = "${var.gateway_id}/workspaces/default"

  body = {
    properties = {
      telemetryExporterType = "OpenTelemetry"
      payloadCapture        = false
      openTelemetry = {
        metricsEndpoint = {
          url = azapi_resource_action.otlp.output.metrics_endpoint
        }
        logsEndpoint = {
          url = azapi_resource_action.otlp.output.logs_endpoint
        }
        tracesEndpoint = {
          url = azapi_resource_action.otlp.output.traces_endpoint
        }
      }
      authentication = {
        managedIdentity = {
          resource = "https://monitor.azure.com"
        }
      }
      telemetry = {
        attributes = var.claim_attributes
      }
    }
  }

  schema_validation_enabled = false
  depends_on                = [azurerm_role_assignment.metrics_publisher]
}
