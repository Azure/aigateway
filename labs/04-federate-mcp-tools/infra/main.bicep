// Lab 04 with azd: "azd up" creates the resource group rg-<environment name>, a gateway with lab 01's template, then
// the learn MCP server that federates the public Microsoft Learn MCP server, and the runtime API key app-first-call.
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Namespace for a second, optional Learn backend, such as docs. Empty registers one backend. azd reads it from MCP_SECOND_NAMESPACE.')
param secondNamespace string = ''

@description('Comma-separated MCP protocol versions, such as 2025-06-18. Empty keeps the current list, or the legacy defaults on a new server. azd reads it from MCP_SUPPORTED_VERSIONS.')
param supportedVersions string = ''

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

module toolServer 'tool-server.bicep' = {
  name: 'aigw-tool-server'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    serverName: 'learn'
    namespace: 'learn'
    secondNamespace: secondNamespace
    supportedVersions: supportedVersions
    apiKeyName: 'app-first-call'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output MCP_ENDPOINT string = toolServer.outputs.mcpEndpoint
