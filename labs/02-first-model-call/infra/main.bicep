// Lab 02 with azd: "azd up" creates the resource group rg-<environment name> with lab 01's gateway and this lab's
// Foundry account and gpt-5-mini deployment, then publishes the deployment through the gateway: the Foundry User
// role, the model provider, the backend model, the alias, and the app-first-call key.
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Tokens per minute that each caller identity can use on the model. azd reads it from TOKENS_PER_MINUTE.')
@minValue(1)
param tokensPerMinute int = 10000

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// Lab 01's template: the gateway with a system-assigned identity.
module gateway '../../01-provision-gateway/infra/gateway.bicep' = {
  name: 'aigw-gateway'
  scope: rg
  params: {
    gatewayName: 'aigw-${suffix}'
    location: location
    tags: tags
  }
}

// The backend: a Foundry account with a gpt-5-mini deployment.
module foundry 'foundry.bicep' = {
  name: 'aigw-foundry'
  scope: rg
  params: {
    accountName: 'aigw${suffix}'
    location: location
    tags: tags
  }
}

// The Foundry User role for the gateway, then the provider, the backend model, the alias, and the key.
module publish 'publish-model.bicep' = {
  name: 'aigw-publish-model'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    foundryAccountId: foundry.outputs.accountId
    deploymentName: foundry.outputs.deploymentName
    tokensPerMinute: tokensPerMinute
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = publish.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = publish.outputs.modelName
output AI_GATEWAY_MODEL string = publish.outputs.aliasName
output AI_GATEWAY_API_KEY_NAME string = publish.outputs.apiKeyName
output FOUNDRY_ACCOUNT_NAME string = foundry.outputs.accountName
