// Lab 06 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then a second alias for the same model with its own token limit.
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Tokens allowed per period for each caller. azd reads it from TOKEN_LIMIT.')
@minValue(1)
param allowedTokens int = 1000

@description('Token limit window. azd reads it from TOKEN_LIMIT_PERIOD.')
@allowed([ 'minute', 'hour', 'day' ])
param period string = 'minute'

@description('Who gets a token counter. azd reads it from TOKEN_LIMIT_COUNTER_KEY.')
@allowed([ 'identity', 'ipAddress' ])
param counterKey array = [ 'identity' ]

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

module limitedAlias 'limited-alias.bicep' = {
  name: 'aigw-limited-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    modelName: base.outputs.modelName
    allowedTokens: allowedTokens
    period: period
    counterKey: counterKey
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = limitedAlias.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
