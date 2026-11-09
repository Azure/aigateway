// Creates the Application Insights destination for AI Gateway telemetry: a Log Analytics workspace and a
// workspace-based Application Insights component.
//
// The lab's main.bicep calls it with azd and sets enableOtlpIngestion. azure.yaml then connects the gateway with
// connect-telemetry.sh and otel-exporter.bicep. You can also deploy it on its own to the resource group of an existing
// gateway, then connect the gateway in the portal: Monitoring › Configure telemetry › Existing Azure Application
// Insights resource. The portal enables OTLP ingestion on the component, grants the gateway's managed identity the
// Monitoring Metrics Publisher role, and creates an OpenTelemetry exporter.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Location for the monitoring resources.')
param location string = resourceGroup().location

@description('Application Insights component name. The portal suggests <gateway>-insights for new destinations.')
param appInsightsName string = '${gatewayName}-insights'

@description('Log Analytics workspace that stores the OTelSpans and OTelLogs tables.')
param logAnalyticsWorkspaceName string = take('${gatewayName}-logs', 63)

@description('Tags applied to the monitoring resources.')
param tags object = {}

@description('Turn on OTLP ingestion on the component, as the portal does when you connect it. Azure then creates a managed Azure Monitor workspace, data collection endpoint, and data collection rule, and the component reports its OTLP endpoints a few minutes later.')
param enableOtlpIngestion bool = false

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  // AzureMonitorWorkspaceIngestionMode isn't in the Bicep types for this API version yet, so union() adds it.
  properties: union(
    {
      Application_Type: 'web'
      WorkspaceResourceId: logAnalyticsWorkspace.id
    },
    enableOtlpIngestion ? { AzureMonitorWorkspaceIngestionMode: 'Enabled' } : {}
  )
}

output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name
output logAnalyticsCustomerId string = logAnalyticsWorkspace.properties.customerId
