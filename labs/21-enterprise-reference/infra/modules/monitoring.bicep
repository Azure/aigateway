// Observability destination for the gateway: a Log Analytics workspace and a workspace-based Application Insights
// component with OTLP ingestion on. Azure then creates the component's OTLP endpoints, a Data Collection Rule, and an
// Azure Monitor workspace for the metrics, in a managed resource group, a few minutes after the deployment.
targetScope = 'resourceGroup'

@description('Location for the monitoring resources.')
param location string = resourceGroup().location

@description('Tags applied to every resource.')
param tags object = {}

@description('Log Analytics workspace name. It stores the gateway telemetry that Application Insights ingests.')
param logAnalyticsWorkspaceName string

@description('Application Insights component name. The AI Gateway portal suggests <gateway>-insights.')
param appInsightsName string

@description('Days to keep data in the Log Analytics workspace.')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: retentionInDays
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
    { AzureMonitorWorkspaceIngestionMode: 'Enabled' }
  )
}

output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
