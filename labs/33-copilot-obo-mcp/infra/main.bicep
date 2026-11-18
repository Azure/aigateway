// Lab 33 with azd: "azd up" creates the resource group rg-<environment name>, a gateway with lab 01's template, the
// protected MCP backend (backend.bicep: the identities, the three app registrations, and the demo MCP server on Azure
// Container Apps), attaches the gateway identity with lab 12's template, then registers the obo-demo MCP server with
// an on-behalf-of endpoint and assigns AI Gateway Tools User on it to you.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and Azure Container Apps are available. List them with az provider show --namespace Microsoft.ApiManagement.')
@metadata({ azd: { type: 'location' } })
param location string

@description('Object ID of the user who calls the tools. azd sets AZURE_PRINCIPAL_ID to the signed-in user.')
param principalId string = ''

@description('Git build context of the MCP server image. azd reads it from MCP_SERVER_SOURCE.')
param mcpServerSource string = 'https://github.com/Azure/aigateway.git#main:labs/33-copilot-obo-mcp/infra/mcp-server'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// Lab 01's template: the gateway, with no model.
module gateway '../../01-provision-gateway/infra/gateway.bicep' = {
  name: 'aigw-gateway'
  scope: rg
  params: {
    gatewayName: 'aigw-${suffix}'
    location: location
    tags: tags
  }
}

module backend 'backend.bicep' = {
  name: 'aigw-obo-backend'
  scope: rg
  params: {
    baseName: 'aigw-lab33-${suffix}'
    location: location
    tags: tags
    mcpServerSource: mcpServerSource
  }
}

// Lab 12's template: attaches the gateway identity and keeps the system-assigned identity.
module gatewayIdentity '../../12-backend-identity/infra/gateway-identity.bicep' = {
  name: 'aigw-gateway-identity'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    location: location
    tags: tags
    identityId: backend.outputs.gatewayIdentityId
  }
}

module toolServer 'obo-tool-server.bicep' = {
  name: 'aigw-obo-tool-server'
  scope: rg
  params: {
    gatewayName: gatewayIdentity.outputs.gatewayName
    serverName: 'obo-demo'
    namespace: 'demo'
    backendUrl: backend.outputs.backendUrl
    tokenExchangeAppId: backend.outputs.tokenExchangeAppId
    gatewayIdentityClientId: backend.outputs.gatewayIdentityClientId
    backendScope: backend.outputs.backendScope
    principalId: principalId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output MCP_SERVER string = 'obo-demo'
output MCP_ENDPOINT string = toolServer.outputs.mcpEndpoint
output BACKEND_URL string = backend.outputs.backendUrl
output BACKEND_APP_ID string = backend.outputs.backendAppId
output BACKEND_SCOPE string = backend.outputs.backendScope
output TOKEN_EXCHANGE_APP_ID string = backend.outputs.tokenExchangeAppId
output CONNECTOR_APP_ID string = backend.outputs.connectorAppId
output GATEWAY_IDENTITY_CLIENT_ID string = backend.outputs.gatewayIdentityClientId
output CONTAINER_APP_NAME string = backend.outputs.containerAppName
