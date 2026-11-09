// Lab 12 with azd: "azd up" creates the resource group rg-<environment name> and the quick start's gateway, Foundry
// model, default alias, and runtime API key. Then it creates a user-assigned identity, grants it Foundry User on
// the Foundry account, and attaches it to the gateway. Set USE_USER_ASSIGNED_IDENTITY to true and run
// "azd provision" to point the Foundry provider at the identity. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Name of the user-assigned managed identity. azd reads it from IDENTITY_NAME.')
param identityName string = 'id-aigateway-backends'

@description('Point the Foundry provider at the user-assigned identity. azd reads it from USE_USER_ASSIGNED_IDENTITY.')
param useUserAssignedIdentity bool = false

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry model behind the default alias, and the app-first-call key. Its
// provider uses the gateway's system-assigned identity.
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

module identity 'backend-identity.bicep' = {
  name: 'aigw-backend-identity'
  scope: rg
  params: {
    identityName: identityName
    location: location
    foundryAccountId: base.outputs.foundryId
  }
}

module gatewayIdentity 'gateway-identity.bicep' = {
  name: 'aigw-gateway-identity'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    location: location
    tags: tags
    identityId: identity.outputs.identityId
  }
}

module provider 'provider.bicep' = if (useUserAssignedIdentity) {
  name: 'aigw-provider-identity'
  scope: rg
  params: {
    gatewayName: gatewayIdentity.outputs.gatewayName
    providerName: base.outputs.providerName
    foundryAccountId: base.outputs.foundryId
    identityClientId: identity.outputs.clientId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
output FOUNDRY_ID string = base.outputs.foundryId
output IDENTITY_NAME string = identityName
output IDENTITY_ID string = identity.outputs.identityId
output IDENTITY_CLIENT_ID string = identity.outputs.clientId
output IDENTITY_PRINCIPAL_ID string = identity.outputs.principalId
output PROVIDER_IDENTITY string = useUserAssignedIdentity ? identity.outputs.clientId : 'system-assigned'
