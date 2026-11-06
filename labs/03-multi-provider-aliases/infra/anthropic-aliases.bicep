// Adds Anthropic to an existing AI Gateway as a custom provider, registers two Claude models, and publishes them
// behind three callable aliases: support-chat and batch-chat, each with its own per-caller token limit, and
// anthropic/<smart model>. main.bicep calls it after the quick start's template, and you can also deploy it on its
// own to a gateway you already have. The Anthropic key is a secure parameter: the gateway stores it, it never
// appears in the deployment history or the outputs, and clients never receive it.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Name of the custom provider to create. It\'s part of the resource ID, so you can\'t change it later.')
param providerName string = 'anthropic'

@secure()
@description('The Anthropic API key that the gateway sends to Anthropic in the x-api-key header.')
param anthropicApiKey string

@description('A fast model that your Anthropic key can call.')
param fastModel string = 'claude-haiku-5-5'

@description('A bigger model that your Anthropic key can call.')
param smartModel string = 'claude-sonnet-5-5'

@description('The backend model behind the support-chat alias: fastModel or smartModel.')
param supportChatModel string = fastModel

@description('Per-caller tokens per minute for the support-chat alias.')
@minValue(1)
param supportChatTokensPerMinute int = 20000

@description('Per-caller tokens per minute for the batch-chat alias.')
@minValue(1)
param batchChatTokensPerMinute int = 2000

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

// Leave /v1 off the endpoint. Anthropic expects the raw key in x-api-key, with no "Bearer" scheme.
#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = {
  parent: workspace
  name: providerName
  properties: {
    kind: 'Custom'
    displayName: 'Anthropic'
    custom: {
      endpoint: 'https://api.anthropic.com'
      authentication: {
        kind: 'ApiKey'
        apiKey: {
          headerName: 'x-api-key'
          value: anthropicApiKey
        }
      }
    }
  }
}

// Custom providers list the provider path in supportedEndpoints and leave out apiFormat. Names may only contain
// lowercase letters, digits, and hyphens; modelName keeps the provider's real model ID.
#disable-next-line BCP081
resource models 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = [for name in [ fastModel, smartModel ]: {
  parent: provider
  name: name
  properties: {
    displayName: name
    supportedEndpoints: [ '/v1/messages' ]
    deployment: {
      modelName: name
    }
  }
}]

var fastModelId = models[0].id
var smartModelId = models[1].id

// The callable name goes in aliasName and can contain "/". The resource name can't, so it uses "-" instead.
var aliases = [
  {
    name: 'support-chat'
    aliasName: 'support-chat'
    modelId: supportChatModel == smartModel ? smartModelId : fastModelId
    tokensPerMinute: supportChatTokensPerMinute
  }
  {
    name: 'batch-chat'
    aliasName: 'batch-chat'
    modelId: fastModelId
    tokensPerMinute: batchChatTokensPerMinute
  }
  {
    name: '${providerName}-${smartModel}'
    aliasName: '${providerName}/${smartModel}'
    modelId: smartModelId
    tokensPerMinute: 0
  }
]

#disable-next-line BCP081
resource aliasResources 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = [for alias in aliases: {
  parent: workspace
  name: alias.name
  properties: {
    aliasName: alias.aliasName
    backendModels: [
      { resourceId: alias.modelId }
    ]
    policies: alias.tokensPerMinute > 0 ? [
      {
        type: 'tokenLimit'
        count: alias.tokensPerMinute
        period: 'minute'
        counterKey: [ 'identity' ]
      }
    ] : []
  }
}]

output providerName string = provider.name
output fastModel string = models[0].name
output smartModel string = models[1].name
output aliasNames array = [for (alias, i) in aliases: aliasResources[i].properties.aliasName]
output messagesUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/anthropic/v1/messages'
