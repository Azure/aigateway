// Lab 30 with azd: "azd up" registers the decision service in Microsoft Entra ID, creates the resource group
// rg-<environment name>, a gateway with lab 01's template, the decision service (hook.bicep), then the learn MCP
// server with the agent hooks policy and the runtime API key app-first-call. azd then deploys the function code from
// infra/hook. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and Flex Consumption are available. List them with az provider show --namespace Microsoft.ApiManagement and az functionapp list-flexconsumption-locations.')
@metadata({ azd: { type: 'location' } })
param location string

@description('What the gateway does when the decision service can\'t answer. azd reads it from HOOK_MODE.')
@allowed([ 'failClosed', 'failOpen' ])
param hookMode string = 'failClosed'

@description('Comma-separated tool name patterns that the decision service denies. azd reads it from HOOK_BLOCKED_TOOLS.')
param blockedTools string = '*code_sample*'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// Microsoft Graph objects don't belong to the resource group: the deployment only runs there.
module registration 'hook-registration.bicep' = {
  name: 'aigw-hook-registration'
  scope: rg
  params: {
    uniqueName: 'aigw-lab30-hook-${suffix}'
  }
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

module hook 'hook.bicep' = {
  name: 'aigw-hook'
  scope: rg
  params: {
    appName: 'func-aigw-hook-${suffix}'
    location: location
    hookClientId: registration.outputs.clientId
    hookAudience: registration.outputs.audience
    gatewayPrincipalId: gateway.outputs.principalId
    blockedTools: blockedTools
    tags: tags
  }
}

module toolServer 'guarded-tool-server.bicep' = {
  name: 'aigw-guarded-tool-server'
  scope: rg
  params: {
    gatewayName: gateway.outputs.gatewayName
    serverName: 'learn'
    hookUrl: hook.outputs.hookUrl
    hookAudience: registration.outputs.audience
    hookMode: hookMode
    apiKeyName: 'app-first-call'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output MCP_SERVER string = 'learn'
output MCP_ENDPOINT string = toolServer.outputs.mcpEndpoint
output HOOK_APP_NAME string = hook.outputs.appName
output HOOK_URL string = hook.outputs.hookUrl
output HOOK_CLIENT_ID string = registration.outputs.clientId
output HOOK_AUDIENCE string = registration.outputs.audience
output HOOK_LOG_WORKSPACE_ID string = hook.outputs.logWorkspaceId
