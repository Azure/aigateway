// The demo MCP backend on Azure Container Apps. An ACR Tasks run builds its image from a Git build context, so you
// don't need Docker, and the deployment waits for the build to finish. Container Apps built-in authentication (Easy Auth)
// rejects every request that doesn't carry a token for the backend's app registration, requested by the token exchange
// app, before it reaches the container. server.py checks the token again and reads the user's claims for the tools.
@minLength(3)
param baseName string
param location string = resourceGroup().location
param tags object = {}

@description('Resource ID of the user-assigned managed identity that pulls the image from the registry.')
param identityId string

@description('Principal ID of the same identity.')
param identityPrincipalId string

@description('Client ID of the MCP backend app registration: the audience of the tokens that the backend accepts.')
param backendAppId string

@description('Client ID of the token exchange app registration: the only app that may request those tokens.')
param tokenExchangeAppId string

@description('Git build context of the image: <repository>.git#<branch>:<folder>.')
param sourceLocation string

@description('Image tag. A new tag builds the image again.')
param imageTag string

var tenantId = tenant().tenantId
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var imageName = 'obo-mcp-server:${imageTag}'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${baseName}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  #disable-next-line BCP334 // baseName has at least 3 characters, so the name has at least 6.
  name: take(replace('acr${baseName}', '-', ''), 50)
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identityPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource image 'Microsoft.ContainerRegistry/registries/taskRuns@2019-06-01-preview' = {
  parent: registry
  name: 'build-obo-mcp-server'
  location: location
  properties: {
    forceUpdateTag: imageTag
    runRequest: {
      type: 'DockerBuildRequest'
      sourceLocation: sourceLocation
      dockerFilePath: 'Dockerfile'
      imageNames: [ imageName ]
      isPushEnabled: true
      platform: {
        os: 'Linux'
        architecture: 'amd64'
      }
    }
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: 'cae-${baseName}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    // Declare the Consumption profile: an environment without workload profiles rejects workloadProfileName.
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource app 'Microsoft.App/containerApps@2025-07-01' = {
  name: 'ca-${baseName}-mcp'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    environmentId: containerEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mcp-server'
          image: '${registry.properties.loginServer}/${imageName}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'AZURE_TENANT_ID', value: tenantId }
            { name: 'BACKEND_CLIENT_ID', value: backendAppId }
            { name: 'REQUIRED_SCOPE', value: 'user_impersonation' }
            { name: 'ALLOWED_CLIENT_IDS', value: tokenExchangeAppId }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000 }
            }
            {
              type: 'Readiness'
              httpGet: { path: '/healthz', port: 8000 }
            }
          ]
        }
      ]
      // One replica avoids a cold start while Microsoft 365 Copilot discovers the tools.
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
  dependsOn: [
    image
    acrPull
  ]
}

resource auth 'Microsoft.App/containerApps/authConfigs@2025-07-01' = {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'Return401'
      excludedPaths: [ '/healthz' ]
    }
    httpSettings: { requireHttps: true }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: backendAppId
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [ backendAppId ]
          defaultAuthorizationPolicy: {
            allowedApplications: [ tokenExchangeAppId ]
          }
        }
      }
    }
  }
}

output mcpUrl string = 'https://${app.properties.configuration.ingress.fqdn}/mcp'
output containerAppName string = app.name
output registryName string = registry.name
