// Declares the learn MCP server of lab 04 with an optional Agent 365 tool threat protection policy, which has Microsoft
// Defender and Microsoft Purview evaluate each tool request (preInvocation), each tool result (postInvocation), or
// both. It assigns AI Gateway Tools User on the server to a user, so that user can call tools with a delegated token,
// and creates a runtime API key. The key is never an output.
// A deployment sends a PUT, which replaces the whole MCP server, so keep this template as its only source of truth.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('MCP server name. It becomes part of the endpoint URL and cannot be changed after creation.')
param serverName string = 'learn'

@description('Evaluate the tool name and arguments before the tool runs.')
param preInvocation bool = true

@description('Evaluate the tool result after the tool returns. The tool has already run.')
param postInvocation bool = true

@description('Object ID of the user who gets AI Gateway Tools User on the MCP server. Empty skips the role assignment.')
param principalId string = ''

@description('Runtime API key to create for the key-only test call.')
param apiKeyName string = 'app-first-call'

// AI Gateway Tools User: call the tools of an MCP server with a Microsoft Entra ID token.
var toolsUserRoleId = 'dce03f8d-857f-4e40-a90d-67770fa6ecd2'

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

#disable-next-line BCP081
resource toolServer 'Microsoft.ApiManagement/aigateways/workspaces/toolServers@2025-09-01-preview' = {
  parent: workspace
  name: serverName
  properties: {
    displayName: 'Microsoft Learn'
    description: 'Search and fetch official Microsoft documentation and code samples.'
    type: 'mcp'
    endpoints: [
      {
        namespace: 'learn'
        kind: 'mcp'
        mcp: {
          url: 'https://learn.microsoft.com/api/mcp'
          transport: 'streamableHttp'
        }
        required: true
      }
    ]
    // A tool threat protection policy needs at least one stage.
    policies: preInvocation || postInvocation
      ? [
          {
            type: 'toolThreatProtection'
            preInvocation: preInvocation
            postInvocation: postInvocation
          }
        ]
      : []
  }
}

resource toolsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(toolServer.id, principalId, toolsUserRoleId)
  scope: toolServer
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', toolsUserRoleId)
  }
}

#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: gateway
  name: apiKeyName
  properties: {}
}

output toolServerId string = toolServer.id
output mcpEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/toolservers/${serverName}/mcp'
