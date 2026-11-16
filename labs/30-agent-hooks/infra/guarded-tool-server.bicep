// Declares the learn MCP server of lab 04 with an agent hooks policy: before each tool call and after each tool
// result, the gateway sends the call to the decision service and follows its allow or deny decision. The gateway signs
// in to the decision service with its system-assigned managed identity. The template also creates a runtime API key,
// which is never an output.
// A deployment sends a PUT, which replaces the whole MCP server, so keep this template as its only source of truth.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('MCP server name. It becomes part of the endpoint URL and cannot be changed after creation.')
param serverName string = 'learn'

@description('HTTPS endpoint of the decision service. Both intervention points share it.')
param hookUrl string

@description('Token audience: the Application ID URI of the decision service\'s app registration.')
param hookAudience string

@description('What the gateway does when the decision service can\'t answer: failClosed blocks the call, failOpen lets it through.')
@allowed([ 'failClosed', 'failOpen' ])
param hookMode string = 'failClosed'

@description('Runtime API key to create for the test calls.')
param apiKeyName string = 'app-first-call'

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2026-11-01' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2026-11-01' existing = {
  parent: gateway
  name: 'default'
}

#disable-next-line BCP081
resource toolServer 'Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01' = {
  parent: workspace
  name: serverName
  properties: {
    toolServerType: 'mcp'
    displayName: 'Microsoft Learn'
    description: 'Search and fetch official Microsoft documentation and code samples.'
    endpoints: [
      {
        namespace: 'learn'
        kind: 'mcp'
        mode: 'failClosed'
        mcp: {
          endpoint: { url: 'https://learn.microsoft.com/api/mcp' }
          transport: 'streamableHttp'
        }
      }
    ]
    policies: [
      {
        id: 'tool-guard'
        type: 'agentHooks'
        scope: 'resource'
        mode: hookMode
        endpoint: { url: hookUrl }
        authentication: { managedIdentity: { resource: hookAudience } }
        // Literal, non-secret headers. The gateway sends them with every hook request, and GET returns them.
        headers: [ { name: 'x-hook-policy', value: 'lab30' } ]
        // Both points inherit the endpoint, mode, authentication, and headers above. A point can override them.
        hooks: {
          preToolCall: {}
          postToolCall: {}
        }
      }
    ]
  }
}

#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01' = {
  parent: gateway
  name: apiKeyName
  properties: {}
}

output toolServerId string = toolServer.id
output mcpEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/toolservers/${serverName}/mcp'
