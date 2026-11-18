// Declares the learn MCP server of lab 04, with its learn and docs backends, plus lab 05's tool controls: the tools
// it publishes (allowList), the tools it refuses to run (blockList), whether clients can reach it (accessState), and a
// request rate limit for each caller. It also creates a runtime API key for the MCP clients. The key is never an output.
// A deployment sends a PUT, which replaces the whole MCP server, so keep this template as its only source of truth.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('MCP server name. It becomes part of the endpoint URL and cannot be changed after creation.')
param serverName string = 'learn'

@description('Tool names or patterns to publish. * matches any number of characters and ? exactly one. ["*"] publishes every tool.')
param allowedTools array = [
  '*_search'
]

@description('Tool names or patterns that the gateway refuses to run. They take precedence over allowedTools.')
param blockedTools array = [
  '*code_sample*'
]

@description('MCP server access: active, or blocked to stop all client traffic without deleting the server.')
@allowed([
  'active'
  'blocked'
])
param serverAccess string = 'active'

@description('Calls that each counter allows per period. 0 removes the request rate limit.')
@minValue(0)
param callsPerPeriod int = 5

@description('Renewal period in seconds, from 1 to 300. The portal offers 30, 60, 120, and 300.')
@minValue(1)
@maxValue(300)
param periodSeconds int = 30

@description('What gets its own counter: ["identity"], ["ipAddress"], both, or [] for one counter that all callers share.')
param counterKey array = [
  'identity'
]

@description('Runtime API key to create for the MCP clients.')
param apiKeyName string = 'app-first-call'

var learnUrl = 'https://learn.microsoft.com/api/mcp'

var rateLimit = {
  type: 'requestRateLimit'
  count: callsPerPeriod
  period: 'PT${periodSeconds}S'
  counterKey: counterKey
}

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
    displayName: 'Microsoft Learn'
    description: 'Search and fetch official Microsoft documentation and code samples.'
    toolServerType: 'mcp'
    accessState: serverAccess
    allowList: allowedTools
    blockList: blockedTools
    endpoints: [
      {
        namespace: 'learn'
        kind: 'mcp'
        mode: 'failClosed'
        mcp: {
          endpoint: {
            url: learnUrl
          }
          transport: 'streamableHttp'
        }
      }
      {
        namespace: 'docs'
        kind: 'mcp'
        mode: 'failOpen'
        mcp: {
          endpoint: {
            url: learnUrl
          }
          transport: 'streamableHttp'
        }
      }
    ]
    policies: callsPerPeriod > 0 ? [ rateLimit ] : []
  }
}

#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01' = {
  parent: gateway
  name: apiKeyName
  properties: {
    displayName: apiKeyName
  }
}

output toolServerId string = toolServer.id
output mcpEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/toolservers/${serverName}/mcp'
