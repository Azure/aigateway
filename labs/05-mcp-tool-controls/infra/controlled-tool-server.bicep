// Declares the learn MCP server of lab 04, with its learn and docs backends, plus lab 05's tool controls: the tools
// it publishes (allowList), the tools it refuses to run (blocked), whether clients can reach it (accessState), and a
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

@description('Renewal period in seconds. The portal offers 30, 60, 120, and 300.')
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
  callsPerPeriod: callsPerPeriod
  periodSeconds: periodSeconds
  counterKey: counterKey
}

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
    accessState: serverAccess
    allowList: allowedTools
    blocked: blockedTools
    endpoints: [
      {
        namespace: 'learn'
        kind: 'mcp'
        mcp: {
          url: learnUrl
          transport: 'streamableHttp'
        }
        required: true
      }
      {
        namespace: 'docs'
        kind: 'mcp'
        mcp: {
          url: learnUrl
          transport: 'streamableHttp'
        }
        required: false
      }
    ]
    policies: callsPerPeriod > 0 ? [ rateLimit ] : []
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
