// Lab 19 with azd: "azd up" creates the resource group rg-<environment name>, a gateway with lab 01's template, then
// the learn MCP server, the AI Gateway Tools User role on it for the signed-in user, and the runtime API key
// app-first-call. The tool threat protection stages are off until you turn them on and run "azd provision".
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Evaluate each tool request before the tool runs. azd reads it from TOOL_THREAT_PRE_INVOCATION.')
param preInvocation bool = false

@description('Evaluate each tool result after the tool returns. azd reads it from TOOL_THREAT_POST_INVOCATION.')
param postInvocation bool = false

@description('Object ID of the user who calls the tools. azd sets AZURE_PRINCIPAL_ID to the signed-in user.')
param principalId string = ''

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

module toolServer 'protected-tool-server.bicep' = {
  name: 'aigw-protected-tool-server'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    serverName: 'learn'
    preInvocation: preInvocation
    postInvocation: postInvocation
    principalId: principalId
    apiKeyName: 'app-first-call'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output MCP_SERVER string = 'learn'
output MCP_ENDPOINT string = toolServer.outputs.mcpEndpoint
