// Azure AI Gateway quick start, deployed with "azd up".
// Creates the resource group rg-<environment name> and everything in resources.bicep, then hands the gateway URL,
// the alias, and the gateway resource ID to azd as environment values. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the Foundry model are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Model to deploy in Foundry. The deployment, the gateway model, and the alias use this name.')
param modelName string = 'gpt-5-mini'

@description('Version of the model to deploy.')
param modelVersion string = '2025-08-07'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'aigw-quickstart'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: 'aigw-${suffix}'
    foundryName: 'aigw${suffix}'
    modelName: modelName
    modelVersion: modelVersion
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = resources.outputs.gatewayName
output AI_GATEWAY_ID string = resources.outputs.gatewayId
output AI_GATEWAY_URL string = resources.outputs.gatewayUrl
output AI_GATEWAY_MODEL string = resources.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = resources.outputs.foundryName
