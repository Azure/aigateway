// Lab 23 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// account, gpt-5-mini alias, and app-first-call key, then reuses lab 06's limited-alias.bicep to publish the
// gpt-5-mini-stream alias with a limit of 1,000 tokens per minute for each caller. The key value is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry account with gpt-5-mini, the gpt-5-mini alias, and a key.
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

// Lab 06's template: a second alias for the same backend model, with a deliberately low token limit.
module streamAlias '../../06-token-limits/infra/limited-alias.bicep' = {
  name: 'aigw-stream-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    modelName: base.outputs.modelName
    aliasName: '${base.outputs.modelName}-stream'
    allowedTokens: 1000
    period: 'minute'
    counterKey: [
      'identity'
    ]
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output AI_GATEWAY_STREAM_ALIAS string = streamAlias.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
