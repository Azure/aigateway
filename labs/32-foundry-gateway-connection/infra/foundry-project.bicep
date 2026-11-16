// The app team's side of the hub and spoke: a Foundry resource and project, each with a system-assigned managed
// identity, and the project's connection to an AI Gateway, the same connection that the Foundry portal's Gateway
// option creates. The project's identity gets AI Gateway Models User on all of the gateway's assets, so the gateway
// accepts the project's calls, and the identity that uses the project gets Foundry User on the Foundry resource.
// Foundry shows the connected model as <connection name>/<alias>.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Resource group of the gateway, when it isn\'t this one.')
param gatewayResourceGroup string = resourceGroup().name

@description('Alias that the project calls. Agents and apps send <connection name>/<alias> as the model.')
param aliasName string = 'gpt-5-mini'

@description('Model and version behind the alias. Foundry lists them with the connected model.')
param modelName string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'

@description('The app team\'s Foundry resource. It\'s also its custom subdomain, so it must be globally unique.')
@minLength(2)
@maxLength(64)
param accountName string

@description('The app team\'s Foundry project.')
param projectName string = 'app-team'

param location string = resourceGroup().location
param tags object = {}

@description('Connection name. The Foundry portal names the connection after the gateway, and so does this template.')
param connectionName string = gatewayName

@description('Send the project\'s requests to the gateway\'s Responses API, like Use the Responses API for upstream requests in the portal. When false, the gateway receives Chat Completions requests.')
param useResponsesApi bool = true

@description('Object ID of the identity that uses the project in the portal and from code. It gets Foundry User on the Foundry resource. Leave it empty to skip the assignment.')
param principalId string = ''

@description('Type of that identity.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param principalType string = 'User'

var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2026-11-01' existing = {
  name: gatewayName
  scope: resourceGroup(gatewayResourceGroup)
}

// 1. The app team's Foundry resource. allowProjectManagement turns on projects, and local auth is off.
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

// 2. The project, with its own identity. The connection signs in to the gateway with it.
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'App team project that uses models published by the ${gatewayName} AI Gateway.'
  }
}

// 3. The connection. Its metadata values are strings, and apimResource and models are JSON documents.
var gatewayUrl = 'https://${gateway.properties.frontend.defaultHostname}'
var gatewayResource = {
  id: gateway.id
  name: gatewayName
  gatewayUrl: gatewayUrl
  location: gateway.location
  subscriptionId: subscription().subscriptionId
  resourceGroup: gatewayResourceGroup
}
var models = [
  {
    name: aliasName
    properties: {
      model: {
        name: modelName
        version: modelVersion
        format: 'OpenAI'
      }
    }
  }
]

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: connectionName
  properties: {
    category: 'ApiManagement'
    target: '${gatewayUrl}/default/models/openai/v1'
    // The connection signs in with the project's identity. Bicep's type definitions don't list this value yet.
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    audience: 'https://azure-api.net/aigateway'
    isSharedToAll: false
    metadata: union(
      {
        apimResourceKind: 'AiGateway'
        apimResource: string(gatewayResource)
        deploymentInPath: 'false'
        inferenceAPIVersion: ''
        models: string(models)
      },
      useResponsesApi ? { upstreamSurface: 'responses' } : {}
    )
  }
}

// 4. AI Gateway Models User for the project's identity on all of the gateway's assets (lab 11's module).
module gatewayRole '../../11-entra-rbac/infra/role-assignment.bicep' = {
  name: 'aigw-project-models-user'
  scope: resourceGroup(gatewayResourceGroup)
  params: {
    gatewayName: gatewayName
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
    role: 'models'
    scope: 'workspace'
  }
}

// 5. Foundry User for you, so that you can use the project's playground and agents and call it from code.
resource foundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: account
  name: guid(account.id, principalId, foundryUserRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
  }
}

output accountName string = account.name
output projectName string = project.name
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'
output projectPrincipalId string = project.identity.principalId
output connectionName string = connection.name
output foundryModel string = '${connection.name}/${aliasName}'
output roleAssignmentId string = gatewayRole.outputs.roleAssignmentId
