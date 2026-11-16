// Publishes TypeSafe's Jev decision model on an existing gateway: a Custom model provider that calls the TypeSafe API
// with your TypeSafe key, the jev-latest model with the System One endpoint, the ticket-triage alias with a request
// rate limit for each caller, and a runtime API key for the triage app. The TypeSafe key is a secure parameter: the
// gateway stores it and never returns it, and it's never an output. Read the runtime key with
// az aigateway api-key list-secrets.
targetScope = 'resourceGroup'

@description('Name of an existing AI Gateway in this resource group.')
param gatewayName string

@secure()
@description('Your TypeSafe API key. The gateway sends it to TypeSafe as Authorization: Bearer <key>.')
param jevApiKey string

@description('Model provider name. It is part of the backend model\'s resource ID.')
param providerName string = 'typesafe'

@description('Base URL of the TypeSafe API, or of another System One-compatible host, including any path prefix.')
param endpointUrl string = 'https://api.typesafe.ai'

@description('A Jev model name that your TypeSafe account can call, such as jev-latest or a pinned version.')
param modelName string = 'jev-latest'

@description('The alias that apps send in the request\'s model field.')
param aliasName string = 'ticket-triage'

@description('Decision requests per minute for each caller identity on the alias. 0 removes the limit.')
@minValue(0)
param requestsPerMinute int = 5

@description('Name of the runtime API key for the triage app.')
param apiKeyName string = 'app-ticket-triage'

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2026-11-01' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2026-11-01' existing = {
  parent: gateway
  name: 'default'
}

// 1. A Custom provider for the TypeSafe API. Its one header carries the TypeSafe key on every call to TypeSafe.
#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01' = {
  parent: workspace
  name: providerName
  properties: {
    modelProviderType: 'Custom'
    displayName: 'TypeSafe'
    description: 'TypeSafe Jev decision models.'
    custom: {
      endpoint: {
        url: endpointUrl
      }
    }
    authentication: {
      headers: [
        {
          name: 'Authorization'
          value: 'Bearer ${jevApiKey}'
        }
      ]
    }
  }
}

// 2. The Jev model. typesafe/v1/systemone is the System One decisions endpoint, written without a leading slash.
#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: modelName
  properties: {
    displayName: modelName
    description: 'TypeSafe Jev decision model.'
    supportedEndpoints: [
      'typesafe/v1/systemone'
    ]
    deployment: {
      modelName: modelName
    }
  }
}

// 3. The alias that apps call, with a limit on decision requests per minute for each caller identity.
#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01' = {
  parent: workspace
  name: aliasName
  properties: {
    aliasName: aliasName
    description: 'Decision alias for support ticket triage.'
    backendModels: [
      {
        resourceId: model.id
      }
    ]
    policies: requestsPerMinute > 0
      ? [
          {
            type: 'requestRateLimit'
            count: requestsPerMinute
            period: 'minute'
            counterKey: [
              'identity'
            ]
          }
        ]
      : []
  }
}

// 4. A runtime API key for the triage app. Its value is never an output.
#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01' = {
  parent: gateway
  name: apiKeyName
  properties: {}
}

output providerName string = provider.name
output modelName string = model.name
output aliasName string = alias.name
output apiKeyName string = apiKey.name
output sdkBaseUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/typesafe'
output decisionsUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/typesafe/v1/systemone'
