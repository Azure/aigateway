// The gateway's OpenTelemetry exporter: sends metrics, logs, and traces to the OTLP endpoints of the Application
// Insights component from monitoring.bicep, the same way the portal's Configure telemetry wizard does, with the
// recommended token claims.
// main.bicep doesn't deploy it. Azure creates the component's OTLP endpoints and their Data Collection Rule a few
// minutes after the deployment, and the gateway's managed identity needs Monitoring Metrics Publisher on that rule
// before the exporter exists. Bicep can't wait for either, and the rule's managed resource group blocks deployments.
// So scripts/connect-telemetry.sh (or .ps1) waits for the endpoints, assigns the role, then deploys this file.
targetScope = 'resourceGroup'

@description('Name of the existing gateway in this resource group.')
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

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2026-11-01' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2026-11-01' existing = {
  parent: aiGateway
  name: 'default'
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// The OTLP properties aren't in the Bicep types for this API version yet. any() skips the type check.
var otlp = any(appInsights.properties)

#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2026-11-01' = {
  parent: defaultWorkspace
  name: exporterName
  properties: {
    telemetryExporterType: 'OpenTelemetry'
    // Prompts and responses can be sensitive and add volume, so payloads stay out of the telemetry.
    payloadCapture: false
    // No applicationInsights link: the portal finds the component through the Data Collection Rule in the endpoints.
    openTelemetry: {
      metricsEndpoint: {
        url: otlp.OTLPMetricsEndpoint
      }
      logsEndpoint: {
        url: otlp.OTLPLogsEndpoint
      }
      tracesEndpoint: {
        url: otlp.OTLPTracesEndpoint
      }
    }
    authentication: {
      managedIdentity: {
        resource: 'https://monitor.azure.com'
      }
    }
    telemetry: {
      attributes: claimAttributes
    }
  }
}

output telemetryExporterId string = telemetryExporter.id
