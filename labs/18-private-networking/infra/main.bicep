// Lab 18 with azd: "azd up" creates the resource group rg-<environment name> with a dedicated Foundry account and
// gpt-5-mini, a virtual network, a new gateway with private routing through the network's integration subnet, a
// private endpoint and private DNS for Foundry, and lab 02's provider, model, private-chat alias, and runtime key.
// Set FOUNDRY_PUBLIC_NETWORK_ACCESS to Disabled and run "azd provision" to turn off Foundry's public access.
// The key value is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Public network access of the lab\'s Foundry account. Set it to Disabled once the private endpoint exists.')
@allowed([
  'Enabled'
  'Disabled'
])
param foundryPublicNetworkAccess string = 'Enabled'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// A Foundry account with gpt-5-mini that only this lab uses, so you can turn off its public access.
module foundry 'foundry.bicep' = {
  name: 'aigw-foundry'
  scope: rg
  params: {
    accountName: 'aigw${suffix}'
    location: location
    tags: tags
    publicNetworkAccess: foundryPublicNetworkAccess
  }
}

// The network, the gateway with private routing, and the Foundry private endpoint with its private DNS zones.
module network 'private-network.bicep' = {
  name: 'aigw-private-network'
  scope: rg
  params: {
    gatewayName: 'aigw-${suffix}'
    location: location
    tags: tags
    foundryAccountId: foundry.outputs.accountId
  }
}

// Lab 02's template: the Foundry User role for the gateway, the provider, the model, the alias, and a runtime key.
module publish '../../02-first-model-call/infra/publish-model.bicep' = {
  name: 'aigw-publish-model'
  scope: rg
  params: {
    gatewayName: network.outputs.gatewayName
    foundryAccountId: foundry.outputs.accountId
    deploymentName: foundry.outputs.deploymentName
    providerName: 'foundry-private'
    aliasName: 'private-chat'
    apiKeyName: 'private-net-lab'
    apiKeyDisplayName: 'private-net-lab'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = network.outputs.gatewayName
output AI_GATEWAY_ID string = network.outputs.gatewayId
output AI_GATEWAY_URL string = network.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = publish.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = publish.outputs.modelName
output AI_GATEWAY_MODEL string = publish.outputs.aliasName
output AI_GATEWAY_KEY_NAME string = publish.outputs.apiKeyName
output AI_GATEWAY_SUBNET_ID string = network.outputs.integrationSubnetId
output FOUNDRY_ACCOUNT_NAME string = foundry.outputs.accountName
output FOUNDRY_ACCOUNT_ID string = foundry.outputs.accountId
output FOUNDRY_ENDPOINT string = foundry.outputs.endpoint
output FOUNDRY_PRIVATE_ENDPOINT_NAME string = network.outputs.foundryPrivateEndpointName
