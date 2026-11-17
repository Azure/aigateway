# Connects the gateway to the destination, like connect-telemetry.sh and otel-exporter.bicep: the gateway's
# managed identity gets Monitoring Metrics Publisher on the Data Collection Rule, then an OpenTelemetry exporter sends
# metrics, logs, and traces to the component's OTLP endpoints, with the token claims in claim_attributes.
locals {
  monitoring_metrics_publisher_role_id = "3913510d-42f4-4e42-8a64-420c390055eb"
  dcr_id                               = azapi_resource_action.otlp.output.dcr_id
}

# The rule lives in the managed resource group. Its deny assignment blocks deployments, which is why Bicep can't
# assign this role, but not the role assignment API that azurerm calls.
resource "azurerm_role_assignment" "metrics_publisher" {
  name                             = uuidv5("url", "${local.dcr_id}/${var.gateway_principal_id}/${local.monitoring_metrics_publisher_role_id}")
  scope                            = local.dcr_id
  role_definition_id               = "/subscriptions/${split("/", local.dcr_id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.monitoring_metrics_publisher_role_id}"
  principal_id                     = var.gateway_principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azapi_resource" "exporter" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2026-11-01"
  name      = var.exporter_name
  parent_id = var.workspace_id

  body = {
    properties = {
      telemetryExporterType = "OpenTelemetry"
      payloadCapture        = var.payload_capture
      # No applicationInsights block: an OpenTelemetry exporter can't carry one.
      openTelemetry = {
        metricsEndpoint = { url = azapi_resource_action.otlp.output.metrics_endpoint }
        logsEndpoint    = { url = azapi_resource_action.otlp.output.logs_endpoint }
        tracesEndpoint  = { url = azapi_resource_action.otlp.output.traces_endpoint }
      }
      # The gateway's system-assigned identity gets a token for Azure Monitor ingestion.
      authentication = {
        managedIdentity = { resource = "https://monitor.azure.com" }
      }
      telemetry = {
        attributes = [
          for a in var.claim_attributes : {
            source  = { kind = "claims", value = a.claim }
            signals = a.signals
          }
        ]
      }
    }
  }

  schema_validation_enabled = false
  depends_on                = [azurerm_role_assignment.metrics_publisher]
}
