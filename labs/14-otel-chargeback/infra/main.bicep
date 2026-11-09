// Lab 14 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then lab 13's Application Insights destination, and lab 11's role so
// that you can call the model with your Microsoft Entra token. azure.yaml then creates lab 13's OpenTelemetry
// exporter with the token claims in otel-exporter.bicepparam. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Object ID of the identity that calls the gateway with Entra tokens. azd sets AZURE_PRINCIPAL_ID to the signed-in user or service principal.')
param principalId string

@description('Type of that identity. azd reads it from AZURE_PRINCIPAL_TYPE, User by default.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param principalType string = 'User'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry model behind the default alias, and the app-first-call key.
module base '../../quickstart/infra/resources.bicep' = {
  name: 'aigw-base'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: 'aigw-${suffix}'
    foundryName: 'aigw${suffix}'
  }
}

// Lab 13's destination: a Log Analytics workspace and an Application Insights component with OTLP ingestion on.
module monitoring '../../13-monitoring/infra/monitoring.bicep' = {
  name: 'aigw-monitoring'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    location: location
    tags: tags
    enableOtlpIngestion: true
  }
}

// Lab 13's OpenTelemetry exporter comes after this deployment, once Azure has created the OTLP endpoints: azure.yaml
// runs lab 13's connect-telemetry.sh, which grants the gateway's identity Monitoring Metrics Publisher on the data
// collection rule, then deploys otel-exporter.bicep with the claims in otel-exporter.bicepparam.

// Lab 11's role assignment: AI Gateway Models User on the gateway, for the Entra calls.
module roleAssignment '../../11-entra-rbac/infra/role-assignment.bicep' = {
  name: 'aigw-role-assignment'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    principalId: principalId
    principalType: principalType
    role: 'models'
    scope: 'gateway'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
output AI_GATEWAY_PRINCIPAL_ID string = base.outputs.gatewayPrincipalId
output APP_INSIGHTS_ID string = monitoring.outputs.appInsightsId
output APP_INSIGHTS_NAME string = monitoring.outputs.appInsightsName
output LOG_ANALYTICS_WORKSPACE_ID string = monitoring.outputs.logAnalyticsWorkspaceId
output AI_GATEWAY_ROLE_ASSIGNMENT_ID string = roleAssignment.outputs.roleAssignmentId
