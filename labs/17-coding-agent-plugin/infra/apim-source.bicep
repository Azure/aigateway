// Optional: a sample Azure API Management instance that serves AI the classic way, to practice a migration to
// AI Gateway. It deploys an APIM BasicV2 instance with a system-assigned identity, a Foundry account with one
// gpt-5-mini deployment, an Azure OpenAI model API with a token limit and a header transformation, a product
// with one subscription, and an MCP server that passes through to the Microsoft Learn MCP server.
// Skip it if you migrate your own APIM instance. APIM BasicV2 and model inference are billed.
// Deploy it with "az deployment group create". It takes about 10 minutes.
targetScope = 'resourceGroup'

@description('API Management instance name. It is also the gateway host name, so it must be globally unique.')
@minLength(1)
@maxLength(50)
param apimName string

@description('Foundry account name. It is also used as the custom subdomain, so it must be globally unique.')
@minLength(2)
@maxLength(64)
param foundryName string

@description('Region for both resources. APIM BasicV2 and the model must be available in this region.')
param location string = resourceGroup().location

@description('Publisher email that API Management requires.')
param publisherEmail string = 'admin@contoso.com'

@description('Tokens per minute that each subscription can spend through the model API.')
@minValue(1)
param tokensPerMinute int = 5000

var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var foundryBackendName = 'foundry-ai-endpoint'

var modelApiPolicy = '''
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="foundry-ai-endpoint" />
    <llm-token-limit counter-key="@(context.Subscription.Id)" tokens-per-minute="{tokens-per-minute}" estimate-prompt-tokens="false" remaining-tokens-header-name="x-remaining-tokens" />
    <set-header name="x-caller-app" exists-action="override">
      <value>@(context.Subscription.Name)</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
'''

module foundry '../../02-first-model-call/infra/foundry.bicep' = {
  name: 'apim-source-foundry'
  params: {
    accountName: foundryName
    location: location
  }
}

resource apim 'Microsoft.ApiManagement/service@2025-09-01-preview' = {
  name: apimName
  location: location
  sku: {
    name: 'BasicV2'
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: 'Contoso AI platform'
  }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryName
  dependsOn: [
    foundry
  ]
}

// Lets APIM call the model deployments with its managed identity, without keys.
resource openAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryName, apim.id, cognitiveServicesOpenAIUserRoleId)
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
  }
}

resource foundryBackend 'Microsoft.ApiManagement/service/backends@2025-09-01-preview' = {
  parent: apim
  name: foundryBackendName
  properties: {
    description: 'Foundry account that serves the model deployments'
    url: '${foundry.outputs.endpoint}openai'
    protocol: 'http'
    resourceId: '${environment().resourceManager}${substring(foundry.outputs.accountId, 1)}'
    // The portal's AI API import authenticates a Foundry backend this way. The published schema omits the property.
    credentials: {
      #disable-next-line BCP037
      managedIdentity: {
        resource: 'https://cognitiveservices.azure.com'
      }
    }
  }
}

resource modelApi 'Microsoft.ApiManagement/service/apis@2025-09-01-preview' = {
  parent: apim
  name: 'azure-openai'
  properties: {
    displayName: 'Azure OpenAI'
    description: 'Azure OpenAI inference, served by the Foundry account'
    path: 'openai'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'subscription-key'
    }
  }
}

var modelOperations = [
  {
    name: 'chat-completions'
    displayName: 'Create a chat completion'
    urlTemplate: '/deployments/{deployment-id}/chat/completions'
  }
  {
    name: 'embeddings'
    displayName: 'Create embeddings'
    urlTemplate: '/deployments/{deployment-id}/embeddings'
  }
  {
    name: 'image-generations'
    displayName: 'Generate images'
    urlTemplate: '/deployments/{deployment-id}/images/generations'
  }
]

resource operations 'Microsoft.ApiManagement/service/apis/operations@2025-09-01-preview' = [
  for operation in modelOperations: {
    parent: modelApi
    name: operation.name
    properties: {
      displayName: operation.displayName
      method: 'POST'
      urlTemplate: operation.urlTemplate
      templateParameters: [
        {
          name: 'deployment-id'
          type: 'string'
          required: true
        }
      ]
    }
  }
]

resource modelApiPolicyResource 'Microsoft.ApiManagement/service/apis/policies@2025-09-01-preview' = {
  parent: modelApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: replace(modelApiPolicy, '{tokens-per-minute}', string(tokensPerMinute))
  }
  dependsOn: [
    foundryBackend
  ]
}

resource product 'Microsoft.ApiManagement/service/products@2025-09-01-preview' = {
  parent: apim
  name: 'ai-apps'
  properties: {
    displayName: 'AI apps'
    description: 'Model access for the internal apps'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

resource productApi 'Microsoft.ApiManagement/service/products/apiLinks@2025-09-01-preview' = {
  parent: product
  name: 'azure-openai'
  properties: {
    apiId: modelApi.id
  }
}

resource subscription 'Microsoft.ApiManagement/service/subscriptions@2025-09-01-preview' = {
  parent: apim
  name: 'ticket-app'
  properties: {
    displayName: 'Ticket app'
    scope: product.id
    state: 'active'
  }
}

resource learnBackend 'Microsoft.ApiManagement/service/backends@2025-09-01-preview' = {
  parent: apim
  name: 'learn-mcp-backend'
  properties: {
    description: 'Microsoft Learn MCP server'
    url: 'https://learn.microsoft.com/api'
    protocol: 'http'
  }
}

resource learnMcp 'Microsoft.ApiManagement/service/apis@2025-09-01-preview' = {
  parent: apim
  name: 'learn-mcp'
  properties: {
    type: 'mcp'
    displayName: 'Microsoft Learn MCP'
    description: 'Microsoft Learn documentation tools'
    path: 'learn-mcp'
    protocols: [
      'https'
    ]
    subscriptionRequired: false
    #disable-next-line BCP037 // The API Management contract accepts backendId on MCP servers; the Bicep type doesn't declare it yet.
    backendId: learnBackend.name
    mcpProperties: {
      transportType: 'streamable'
    }
  }
}

output apimName string = apim.name
output apimGatewayUrl string = apim.properties.gatewayUrl
output foundryAccountName string = foundry.outputs.accountName
output deploymentName string = foundry.outputs.deploymentName
