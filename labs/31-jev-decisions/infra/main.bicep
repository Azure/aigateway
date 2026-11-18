// Lab 31 with azd: "azd up" creates the resource group rg-<environment name> and a gateway with lab 01's template,
// then publishes TypeSafe's Jev decision model with jev-decisions.bicep: a Custom provider, the jev-latest model, the
// ticket-triage alias with a request rate limit, and the app-ticket-triage key. No Foundry account is needed. The
// TypeSafe key comes from JEV_API_KEY in the azd environment and is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@secure()
@description('Your TypeSafe API key. azd reads it from JEV_API_KEY.')
param jevApiKey string

@description('A Jev model name that your TypeSafe account can call. azd reads it from JEV_MODEL.')
param jevModel string = 'jev-latest'

@description('Decision requests per minute for each caller on the ticket-triage alias, or 0 for no limit. azd reads it from DECISIONS_PER_MINUTE.')
@minValue(0)
param decisionsPerMinute int = 5

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// Lab 01's template: a gateway with a system-assigned managed identity.
module gateway '../../01-provision-gateway/infra/gateway.bicep' = {
  name: 'aigw-gateway'
  scope: rg
  params: {
    gatewayName: 'aigw-${suffix}'
    location: location
    tags: tags
  }
}

// This lab's template: the TypeSafe provider, the Jev model, the ticket-triage alias, and the runtime key.
module jev 'jev-decisions.bicep' = {
  name: 'aigw-jev-decisions'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    jevApiKey: jevApiKey
    modelName: jevModel
    requestsPerMinute: decisionsPerMinute
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = jev.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = jev.outputs.modelName
output AI_GATEWAY_MODEL string = jev.outputs.aliasName
output AI_GATEWAY_API_KEY_NAME string = jev.outputs.apiKeyName
output JEV_SDK_BASE_URL string = jev.outputs.sdkBaseUrl
output JEV_DECISIONS_URL string = jev.outputs.decisionsUrl
