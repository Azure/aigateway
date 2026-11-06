// Connects an AI Gateway to Application Insights over OpenTelemetry, the same way the portal's Configure telemetry
// wizard does: an OpenTelemetry exporter that sends metrics, logs, and traces to the component's OTLP endpoints, with
// the token claims to add to the telemetry.
// Deploy it only once two things are in place, or the exporter fails validation or gets empty endpoints:
//   - The component reports its OTLP endpoints. Azure creates them, with a Data Collection Rule, a few minutes after
//     OTLP ingestion turns on (monitoring.bicep with enableOtlpIngestion=true).
//   - The gateway's system-assigned identity has Monitoring Metrics Publisher on that rule. Azure keeps the rule in a
//     managed resource group whose deny assignment blocks deployments, so Bicep can't assign the role.
// Neither can happen inside the deployment that turns ingestion on. So the lab's azure.yaml runs connect-telemetry.sh
// after "azd provision": it waits for the endpoints, assigns the role, then deploys this file with
// otel-exporter.bicepparam. You can also deploy it on your own, to the resource group of an existing gateway and
// component, once both are in place.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Application Insights component in this resource group, with OTLP ingestion on.')
param appInsightsName string

@description('Name of the telemetry exporter. The portal names it appinsights.')
param exporterName string = 'appinsights'

@description('Token claims to add to the telemetry, and the signals that carry each one. The default is the portal\'s "Include recommended token claims in telemetry".')
param claimAttributes array = [
  {
    source: { kind: 'claims', value: 'tid' }
    signals: ['logs', 'traces', 'metrics']
  }
  {
    source: { kind: 'claims', value: 'oid' }
    signals: ['logs', 'traces', 'metrics']
  }
  {
    source: { kind: 'claims', value: 'appid' }
    signals: ['logs', 'traces']
  }
  {
    source: { kind: 'claims', value: 'azp' }
    signals: ['logs', 'traces']
  }
]

@description('Log request and response payloads. Off by default: prompts and responses can be sensitive and add volume.')
param payloadCapture bool = false

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// The OTLP properties aren't in the Bicep types for this API version yet. any() skips the type check.
var otlp = any(appInsights.properties)

#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: exporterName
  properties: {
    kind: 'OpenTelemetry'
    payloadCapture: payloadCapture
    applicationInsights: {
      resourceId: appInsights.id
    }
    openTelemetry: {
      metricsEndpoint: otlp.OTLPMetricsEndpoint
      logsEndpoint: otlp.OTLPLogsEndpoint
      tracesEndpoint: otlp.OTLPTracesEndpoint
      credentials: {
        managedIdentity: {
          resource: 'https://monitor.azure.com'
        }
      }
    }
    telemetry: {
      attributes: claimAttributes
    }
  }
}

output telemetryExporterId string = telemetryExporter.id
output telemetryExporterName string = telemetryExporter.name
