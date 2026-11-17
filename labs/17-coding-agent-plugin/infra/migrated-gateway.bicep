// The infrastructure-as-code path of the migration: the AI Gateway that the settled plan.json describes for the
// sample source (apim-source.bicep), as one Bicep template. Compare it with what your coding agent writes from your
// own plan. It deploys a gateway with a system-assigned identity, grants that identity the Foundry User role on
// the source's Foundry account, and creates what the plan maps:
// - the backend foundry-ai-endpoint as a Foundry model provider, on the account's root endpoint (not APIM's /openai
//   backend URL), signing in with the gateway's identity
// - the deployment gpt-5-mini as a model, with the llm-token-limit policy as a per-caller tokenLimit
// - an alias with the model's name, so apps keep sending "model": "gpt-5-mini" (decision use-model-names)
// - the learn-mcp MCP API as a federated MCP server with the namespace learn-mcp
// - one runtime key for the ticket-app subscription (decision gateway-key-per-consumer). Every gateway also has a
//   built-in master key.
// What stays out, as decided: the image generation operation stays on APIM (split), the x-caller-app header has
// no equivalent (accept), and telemetry uses the gateway's built-in metrics (gateway-metrics-only).
// Deploy it with "az deployment group create". It takes about 2 minutes.
targetScope = 'resourceGroup'

@description('Name of the new gateway. It becomes the first label of the runtime host name (max 24 characters).')
@minLength(1)
@maxLength(24)
param gatewayName string

@description('Region for the gateway. Pick one where AI Gateway is available.')
param location string = resourceGroup().location

@description('Resource ID of the source\'s Foundry account, the one that the APIM backend foundry-ai-endpoint calls.')
param foundryAccountId string

@description('Deployment that the source\'s model API serves, and the name of the model and alias on the gateway.')
param deploymentName string = 'gpt-5-mini'

@description('Version of the deployed model, from the plan\'s deploymentConfig.')
param modelVersion string = '2025-08-07'

@description('Tokens per minute for each caller, from the source\'s llm-token-limit policy.')
@minValue(1)
param tokensPerMinute int = 5000

var foundryAccountName = last(split(foundryAccountId, '/'))
var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  name: foundryAccountName
}

// The provider calls the account's root endpoint. APIM's backend URL ends in /openai, which the gateway can't use.
var foundryEndpoint = foundryAccount.properties.endpoint
var rootEndpoint = endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2026-11-01' = {
  name: gatewayName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2026-11-01' existing = {
  parent: gateway
  name: 'default'
}

// The plan's prerequisite prereq:foundry-rbac: the source's identity can't carry over, so the new one gets the grant.
module foundryUserRole '../../02-first-model-call/infra/foundry-user-role.bicep' = {
  name: take('foundry-user-${uniqueString(gateway.id, foundryAccountId)}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    foundryAccountName: foundryAccountName
    gatewayPrincipalId: gateway.identity.principalId
    gatewayResourceId: gateway.id
  }
}

#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01' = {
  parent: workspace
  name: 'foundry-ai-endpoint'
  dependsOn: [
    foundryUserRole
  ]
  properties: {
    modelProviderType: 'Foundry'
    displayName: 'foundry-ai-endpoint'
    description: 'Migrated from the API Management backend foundry-ai-endpoint.'
    foundry: {
      endpoint: {
        url: rootEndpoint
      }
      resourceIds: [
        foundryAccountId
      ]
    }
    authentication: {
      managedIdentity: {
        resource: 'https://cognitiveservices.azure.com/'
      }
    }
  }
}

#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: deploymentName
  properties: {
    displayName: deploymentName
    description: 'Migrated from the API Management model API azure-openai.'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${deploymentName}'
      modelName: deploymentName
      modelVersion: modelVersion
    }
    // llm-token-limit counted per APIM subscription. The gateway counts per caller identity: each key is one.
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: tokensPerMinute
        counterKey: [
          'identity'
        ]
      }
    ]
  }
}

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01' = {
  parent: workspace
  name: deploymentName
  properties: {
    backendModels: [
      { resourceId: model.id }
    ]
  }
}

#disable-next-line BCP081
resource toolServer 'Microsoft.ApiManagement/aigateways/workspaces/toolServers@2026-11-01' = {
  parent: workspace
  name: 'learn-mcp'
  properties: {
    displayName: 'learn-mcp'
    description: 'Migrated from the API Management MCP server learn-mcp.'
    toolServerType: 'mcp'
    endpoints: [
      {
        namespace: 'learn-mcp'
        kind: 'mcp'
        mode: 'failClosed'
        mcp: {
          endpoint: {
            url: 'https://learn.microsoft.com/api/mcp'
          }
          transport: 'streamableHttp'
        }
      }
    ]
  }
}

// One key for each APIM subscription. Key values never carry over: the gateway generates new ones.
#disable-next-line BCP081
resource ticketAppKey 'Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01' = {
  parent: gateway
  name: 'ticket-app'
  properties: {
    displayName: 'Ticket app'
  }
}

output gatewayName string = gateway.name
output gatewayId string = gateway.id
output gatewayUrl string = 'https://${gateway.properties.frontend.defaultHostname}'
output modelEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/openai/v1'
output mcpEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/toolservers/${toolServer.name}/mcp'
output apiKeyName string = ticketAppKey.name
