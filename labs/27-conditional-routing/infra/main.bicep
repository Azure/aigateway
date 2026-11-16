// Lab 27 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then deploys a research model in the same Foundry account and publishes
// the chat alias, which routes by request header (conditions) or keeps each session on one backend model (affinity).
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Research model to deploy in Foundry and route to. azd reads it from RESEARCH_MODEL.')
param researchModelName string = 'gpt-6.1-sol'

@description('Version of the research model. azd reads it from RESEARCH_MODEL_VERSION.')
param researchModelVersion string = '2026-09-29'

@description('conditions: x-workload: research requests go to the research model, the rest to gpt-5-mini. affinity: both models share the traffic, and each session stays on one of them. azd reads it from ROUTING_MODE.')
@allowed([
  'conditions'
  'affinity'
])
param routingMode string = 'conditions'

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

// The research deployment, in the same Foundry account. The gateway's Foundry User role already covers it.
module researchDeployment 'research-deployment.bicep' = {
  name: 'aigw-research-deployment'
  scope: rg
  params: {
    foundryName: base.outputs.foundryName
    modelName: researchModelName
    modelVersion: researchModelVersion
  }
}

module routing 'conditional-alias.bicep' = {
  name: 'aigw-conditional-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    generalModelName: base.outputs.modelName
    foundryAccountId: researchDeployment.outputs.foundryId
    researchDeploymentName: researchDeployment.outputs.deploymentName
    researchModelVersion: researchModelVersion
    aliasName: 'chat'
    routingMode: routingMode
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_RESEARCH_MODEL string = routing.outputs.researchModelName
output AI_GATEWAY_MODEL string = routing.outputs.aliasName
output AI_GATEWAY_ROUTING_MODE string = routing.outputs.routingMode
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
