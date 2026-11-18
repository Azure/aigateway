// Registers the demo MCP backend as the obo-demo MCP server of an existing AI Gateway. Its endpoint signs in with
// Microsoft Entra ID on-behalf-of (OBO): for each call, the gateway exchanges the caller's token for a token to the
// backend's API, issued to the same user. It signs in as the token exchange app with the gateway's user-assigned
// managed identity, which the gateway must already have. The template also assigns AI Gateway Tools User on the
// server to a user, so that user can call the tools.
// A deployment sends a PUT, which replaces the whole MCP server, so keep this template as its only source of truth.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('MCP server name. It becomes part of the endpoint URL and cannot be changed after creation.')
param serverName string = 'obo-demo'

@description('Namespace of the backend. Its tools are published as <namespace>_<tool>.')
param namespace string = 'demo'

@description('URL of the MCP backend (Streamable HTTP).')
param backendUrl string

@description('Client ID of the token exchange app registration that the gateway signs in as.')
param tokenExchangeAppId string

@description('Client ID (not principal ID) of the gateway\'s user-assigned managed identity that signs in as that app.')
param gatewayIdentityClientId string

@description('Scope of the backend\'s API that the gateway requests: api://<backend client ID>/user_impersonation.')
param backendScope string

@description('MCP protocol versions the server supports. Microsoft 365 Copilot proposes 2025-11-25.')
param versions array = [
  '2025-11-25'
  '2025-06-18'
  '2025-03-26'
]

@description('Object ID of the user who gets AI Gateway Tools User on the MCP server. Empty skips the role assignment.')
param principalId string = ''

// AI Gateway Tools User: call the tools of an MCP server with a Microsoft Entra ID token.
var toolsUserRoleId = 'dce03f8d-857f-4e40-a90d-67770fa6ecd2'

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
    displayName: 'OBO demo'
    description: 'Demo MCP server on Azure Container Apps, called as the signed-in user with Microsoft Entra ID on-behalf-of.'
    toolServerType: 'mcp'
    accessState: 'active'
    versions: versions
    allowList: [ '*' ]
    endpoints: [
      {
        namespace: namespace
        kind: 'mcp'
        mode: 'failClosed'
        mcp: {
          endpoint: { url: backendUrl }
          transport: 'streamableHttp'
        }
        authentication: {
          oauth2: {
            grantType: 'tokenExchange'
            tokenExchange: {
              profile: 'entraOnBehalfOf'
              federatedClientApplication: {
                applicationId: tokenExchangeAppId
                appCredential: {
                  type: 'userAssignedManagedIdentity'
                  clientId: gatewayIdentityClientId
                }
              }
              // A scope of the backend's API. The gateway rejects /.default.
              scopes: [ backendScope ]
            }
          }
        }
      }
    ]
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

output toolServerId string = toolServer.id
output mcpEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/toolservers/${serverName}/mcp'
