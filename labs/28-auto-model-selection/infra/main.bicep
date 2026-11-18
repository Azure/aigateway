// Lab 28 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then deploys gpt-5.5 in the same Foundry account and publishes the auto
// alias, which lets Model Router pick gpt-5-mini or gpt-5.5 for each prompt. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Higher-quality model to deploy in Foundry. It must be a model that Model Router supports. azd reads it from LARGE_MODEL.')
param largeModelName string = 'gpt-5.5'

@description('Version of the higher-quality model. azd reads it from LARGE_MODEL_VERSION.')
param largeModelVersion string = '2026-04-24'

@description('What Model Router favors: Balanced, Cost, or Quality. azd reads it from AUTO_OBJECTIVE.')
@allowed([
  'Balanced'
  'Cost'
  'Quality'
])
param objective string = 'Balanced'

@description('What callers may override per request: objective, model, both, or none. azd reads it from AUTO_ALLOWED_OVERRIDES, for example ["model","objective"].')
param allowedRequestOverrides ('model' | 'objective' | 'filterModelsForToolCompatibility' | 'filterModelsForParameterCompatibility')[] = []

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, gpt-5-mini behind the default alias, and the app-first-call key.
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

// The higher-quality deployment, in the same Foundry account. The gateway's Foundry User role already covers it.
module largeDeployment 'large-deployment.bicep' = {
  name: 'aigw-large-deployment'
  scope: rg
  params: {
    foundryName: base.outputs.foundryName
    modelName: largeModelName
    modelVersion: largeModelVersion
  }
}

module auto 'auto-alias.bicep' = {
  name: 'aigw-auto-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    smallModelName: base.outputs.modelName
    smallSelectorModelName: 'gpt-5-mini'
    foundryAccountId: largeDeployment.outputs.foundryId
    largeDeploymentName: largeDeployment.outputs.deploymentName
    largeModelName: largeModelName
    largeModelVersion: largeModelVersion
    largeBackendModelName: replace(largeModelName, '.', '-')
    aliasName: 'auto'
    objective: objective
    allowedRequestOverrides: allowedRequestOverrides
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_LARGE_MODEL string = largeModelName
output AI_GATEWAY_LARGE_BACKEND_MODEL string = auto.outputs.largeBackendModelName
output AI_GATEWAY_MODEL string = auto.outputs.aliasName
output AI_GATEWAY_OBJECTIVE string = auto.outputs.objective
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
