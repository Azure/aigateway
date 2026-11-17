// Lab 32 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, and default alias (the platform team's hub), then the app team's Foundry resource and project (the spoke),
// the project's connection to the gateway, AI Gateway Models User for the project's identity, and Foundry User for
// you on the app team's Foundry resource.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway, Foundry Agent Service, and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Object ID of the identity that uses the Foundry project. azd sets AZURE_PRINCIPAL_ID to the signed-in user or service principal.')
param principalId string

@description('Type of that identity. azd reads it from AZURE_PRINCIPAL_TYPE, User by default.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param principalType string = 'User'

@description('Name of the app team\'s Foundry project. azd reads it from FOUNDRY_PROJECT_NAME.')
param projectName string = 'app-team'

@description('Send the project\'s requests to the gateway\'s Responses API. azd reads it from FOUNDRY_USE_RESPONSES_API.')
param useResponsesApi bool = true

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

// The app team's Foundry resource and project, the connection, and the roles.
module app 'foundry-project.bicep' = {
  name: 'aigw-foundry-project'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: base.outputs.gatewayName
    aliasName: base.outputs.aliasName
    modelName: base.outputs.modelName
    modelVersion: base.outputs.modelVersion
    accountName: 'aigw${suffix}-apps'
    projectName: projectName
    useResponsesApi: useResponsesApi
    principalId: principalId
    principalType: principalType
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
output FOUNDRY_APP_ACCOUNT_NAME string = app.outputs.accountName
output FOUNDRY_PROJECT_NAME string = app.outputs.projectName
output FOUNDRY_PROJECT_ENDPOINT string = app.outputs.projectEndpoint
output FOUNDRY_CONNECTION_NAME string = app.outputs.connectionName
output FOUNDRY_MODEL string = app.outputs.foundryModel
