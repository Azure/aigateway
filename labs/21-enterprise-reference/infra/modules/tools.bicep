// Federates the public Microsoft Learn MCP server behind the gateway as one governed MCP server, and optionally gives
// Microsoft Entra principals the AI Gateway Tools User role on it. Clients connect to
// https://<gateway-host>/default/toolservers/<serverName>/mcp and see tools named <namespace>___<tool>.
targetScope = 'resourceGroup'

import { principal } from './types.bicep'

@description('Name of the existing gateway in this resource group.')
param gatewayName string

@description('MCP server name. It becomes part of the endpoint URL and can\'t be changed after creation.')
param serverName string = 'learn'

@description('Display name shown in the portal catalog.')
param displayName string = 'Microsoft Learn'

@description('Description that helps people and agents understand what the tools do.')
param serverDescription string = 'Search and fetch official Microsoft documentation and code samples.'

@description('Namespace prefix for the backend\'s tools.')
param namespace string = 'learn'

@description('URL of the backend MCP server (Streamable HTTP).')
param mcpUrl string = 'https://learn.microsoft.com/api/mcp'

@description('Microsoft Entra principals that get the AI Gateway Tools User role on this MCP server.')
param toolUsers principal[] = []

var aiGatewayToolsUserRoleDefinitionId = 'dce03f8d-857f-4e40-a90d-67770fa6ecd2'

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

#disable-next-line BCP081
resource toolServer 'Microsoft.ApiManagement/aigateways/workspaces/toolServers@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: serverName
  properties: {
    displayName: displayName
    description: serverDescription
    type: 'mcp'
    endpoints: [
      {
        namespace: namespace
        kind: 'mcp'
        mcp: {
          url: mcpUrl
          transport: 'streamableHttp'
        }
      }
    ]
  }
}

resource toolServerUsers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for user in toolUsers: {
  scope: toolServer
  name: guid(toolServer.id, user.principalId, aiGatewayToolsUserRoleDefinitionId)
  properties: {
    principalId: user.principalId
    principalType: user.principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiGatewayToolsUserRoleDefinitionId)
  }
}]

output toolServerName string = toolServer.name
output toolServerId string = toolServer.id
output mcpEndpoint string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/toolservers/${serverName}/mcp'
