// Lab 07 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then the app-dev and support-bot keys and a second alias for the same
// model with a cost limit and per-caller overrides. Runtime API key values are never outputs.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Default budget for each caller, in US dollars. azd reads it from COST_LIMIT_AMOUNT.')
param budgetAmount string = '5'

@description('Renewal period. azd reads it from COST_LIMIT_PERIOD.')
@allowed([ 'hour', 'day', 'week', 'month', 'year' ])
param period string = 'day'

@description('Budget for the support-bot key, in US dollars. azd reads it from COST_LIMIT_OVERRIDE_AMOUNT.')
param overrideAmount string = '50'

@description('Object ID of the Microsoft Entra identity that gets its own budget. azd sets AZURE_PRINCIPAL_ID to yours.')
param entraObjectId string = ''

@description('Budget for that Microsoft Entra identity, in US dollars. azd reads it from COST_LIMIT_ENTRA_AMOUNT.')
param entraAmount string = '20'

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

module budgetAlias 'budget-alias.bicep' = {
  name: 'aigw-budget-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    modelName: base.outputs.modelName
    budgetAmount: budgetAmount
    period: period
    overrideAmount: overrideAmount
    entraObjectId: entraObjectId
    entraAmount: entraAmount
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = budgetAlias.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
