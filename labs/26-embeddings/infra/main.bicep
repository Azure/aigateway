// Lab 26 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// account, gpt-5-mini model, default alias, and runtime API key, then deploys text-embedding-3-small in the same
// Foundry account and publishes it through the gateway with its own alias and token limit.
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway, gpt-5-mini, and text-embedding-3-small are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Tokens per minute that each caller identity can send to the embedding model. azd reads it from EMBEDDINGS_TOKENS_PER_MINUTE.')
@minValue(1)
param embeddingsTokensPerMinute int = 2000

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

// The embedding deployment, in the same Foundry account. The gateway's Foundry User role already covers it.
module embeddingsDeployment 'embeddings-deployment.bicep' = {
  name: 'aigw-embeddings-deployment'
  scope: rg
  params: {
    foundryName: base.outputs.foundryName
  }
}

module embeddings 'publish-embeddings.bicep' = {
  name: 'aigw-publish-embeddings'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    deploymentId: embeddingsDeployment.outputs.deploymentId
    deploymentModelName: embeddingsDeployment.outputs.deploymentName
    modelVersion: embeddingsDeployment.outputs.modelVersion
    tokensPerMinute: embeddingsTokensPerMinute
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output AI_GATEWAY_EMBEDDINGS_MODEL string = embeddings.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
