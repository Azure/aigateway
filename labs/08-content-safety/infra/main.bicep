// Lab 08 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then a second alias for the same model with a content safety policy.
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Threshold for Hate. azd reads it from CONTENT_SAFETY_HATE.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param hateSeverity string = 'Medium'

@description('Threshold for Self-harm. azd reads it from CONTENT_SAFETY_SELF_HARM.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param selfHarmSeverity string = 'Medium'

@description('Threshold for Sexual. azd reads it from CONTENT_SAFETY_SEXUAL.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param sexualSeverity string = 'Medium'

@description('Threshold for Violence. azd reads it from CONTENT_SAFETY_VIOLENCE.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param violenceSeverity string = 'Low'

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

module safeAlias 'safe-alias.bicep' = {
  name: 'aigw-safe-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    modelName: base.outputs.modelName
    hateSeverity: hateSeverity
    selfHarmSeverity: selfHarmSeverity
    sexualSeverity: sexualSeverity
    violenceSeverity: violenceSeverity
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = safeAlias.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
