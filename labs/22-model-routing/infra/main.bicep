// Lab 22 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then deploys a candidate model in the same Foundry account and publishes
// the chat alias, which routes across both models by weight or by priority. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Candidate model to deploy in Foundry and route to. azd reads it from CANDIDATE_MODEL.')
param candidateModelName string = 'gpt-6.1-sol'

@description('Version of the candidate model. azd reads it from CANDIDATE_MODEL_VERSION.')
param candidateModelVersion string = '2026-09-29'

@description('weighted: both models share priority 0 and split traffic by weight. priority: the primary is preferred. azd reads it from ROUTING_STRATEGY.')
@allowed([
  'weighted'
  'priority'
])
param strategy string = 'weighted'

@description('Weighted strategy only: the candidate weight. The primary gets 100 minus this value. azd reads it from ROUTING_CANDIDATE_WEIGHT.')
@minValue(1)
@maxValue(99)
param candidateWeight int = 20

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

// The candidate deployment, in the same Foundry account. The gateway's Foundry User role already covers it.
module candidate 'candidate-deployment.bicep' = {
  name: 'aigw-candidate-deployment'
  scope: rg
  params: {
    foundryName: base.outputs.foundryName
    modelName: candidateModelName
    modelVersion: candidateModelVersion
  }
}

module routing 'alias-routing.bicep' = {
  name: 'aigw-alias-routing'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    primaryModelName: base.outputs.modelName
    foundryAccountId: candidate.outputs.foundryId
    candidateDeploymentName: candidate.outputs.deploymentName
    candidateModelVersion: candidateModelVersion
    aliasName: 'chat'
    strategy: strategy
    candidateWeight: candidateWeight
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_CANDIDATE_MODEL string = routing.outputs.candidateModelName
output AI_GATEWAY_MODEL string = routing.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
