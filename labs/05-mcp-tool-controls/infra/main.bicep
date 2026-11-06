// Lab 05 with azd: "azd up" creates the resource group rg-<environment name>, a gateway with lab 01's template, then
// the learn MCP server with its tool controls and request rate limit, and the runtime API key app-first-call.
// The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Tool names or patterns to publish. azd reads it from MCP_ALLOWED_TOOLS.')
param allowedTools array = [
  '*_search'
]

@description('Tool names or patterns that the gateway refuses to run. azd reads it from MCP_BLOCKED_TOOLS.')
param blockedTools array = [
  '*code_sample*'
]

@description('MCP server access: active or blocked. azd reads it from MCP_SERVER_ACCESS.')
@allowed([
  'active'
  'blocked'
])
param serverAccess string = 'active'

@description('Calls per period for each counter, or 0 for no limit. azd reads it from REQUEST_RATE_LIMIT.')
@minValue(0)
param callsPerPeriod int = 5

@description('Renewal period in seconds. azd reads it from REQUEST_RATE_LIMIT_PERIOD.')
param periodSeconds int = 30

@description('Counter dimensions, such as ["identity"]. azd reads it from REQUEST_RATE_LIMIT_COUNTER_KEY.')
param counterKey array = [
  'identity'
]

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

module toolServer 'controlled-tool-server.bicep' = {
  name: 'aigw-controlled-tool-server'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    serverName: 'learn'
    allowedTools: allowedTools
    blockedTools: blockedTools
    serverAccess: serverAccess
    callsPerPeriod: callsPerPeriod
    periodSeconds: periodSeconds
    counterKey: counterKey
    apiKeyName: 'app-first-call'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output MCP_ENDPOINT string = toolServer.outputs.mcpEndpoint
