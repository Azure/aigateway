// Lab 30: the agent hooks decision service. A Python function app on the Flex Consumption plan, with:
// - App Service Authentication (Easy Auth), which accepts only Microsoft Entra tokens for the hook's app registration
//   from the gateway's managed identity, and answers 401 to every other request.
// - A private storage account (no public network access, no shared keys) that the app reaches through a virtual
//   network and a private endpoint, with its managed identity. That works in subscriptions that block public storage.
// - Application Insights with Microsoft Entra authentication, for the decision log.
// The code is deployed separately: az functionapp deployment source config-zip, or azd deploy.

@description('Name of the function app. It must be globally unique: the host name is <name>.azurewebsites.net.')
@minLength(2)
@maxLength(32)
param appName string

@description('Region of the function app. Pick one where Flex Consumption is available (az functionapp list-flexconsumption-locations).')
param location string = resourceGroup().location

@description('Application (client) ID of the hook\'s app registration. Easy Auth accepts tokens issued for it.')
param hookClientId string

@description('Application ID URI of the hook\'s app registration. The gateway asks for tokens with this audience.')
param hookAudience string

@description('Object (principal) ID of the gateway\'s system-assigned managed identity: the only caller Easy Auth lets in.')
param gatewayPrincipalId string

@description('Comma-separated tool name patterns that the hook always denies before the call.')
param blockedTools string = '*code_sample*'

@description('Tags for every resource.')
param tags object = {}

var suffix = uniqueString(resourceGroup().id, appName)
var storageName = take('sthook${suffix}', 24)
var deploymentContainer = 'app-package-${take(toLower(appName), 32)}'
var blobPrivateDnsZone = 'privatelink.blob.${environment().suffixes.storage}'

// Role definitions: Storage Blob Data Owner (host storage and deployment package) and Monitoring Metrics Publisher
// (Application Insights with Microsoft Entra authentication).
var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var metricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${appName}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [ '10.30.0.0/16' ] }
    subnets: [
      {
        // Flex Consumption joins this subnet for outbound traffic, so the app reaches the private storage account.
        name: 'app'
        properties: {
          addressPrefix: '10.30.1.0/24'
          delegations: [ { name: 'flex', properties: { serviceName: 'Microsoft.App/environments' } } ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.30.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Disabled'
    minimumTlsVersion: 'TLS1_2'
    networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
  }

  resource blobService 'blobServices' = {
    name: 'default'

    resource packages 'containers' = {
      name: deploymentContainer
    }
  }
}

resource dnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: blobPrivateDnsZone
  location: 'global'
  tags: tags

  resource link 'virtualNetworkLinks' = {
    name: 'link-${vnet.name}'
    location: 'global'
    properties: {
      registrationEnabled: false
      virtualNetwork: { id: vnet.id }
    }
  }
}

resource blobEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${storage.name}-blob'
  location: location
  tags: tags
  properties: {
    subnet: { id: vnet.properties.subnets[1].id }
    privateLinkServiceConnections: [
      {
        name: 'blob'
        properties: { privateLinkServiceId: storage.id, groupIds: [ 'blob' ] }
      }
    ]
  }

  resource zoneGroup 'privateDnsZoneGroups' = {
    name: 'default'
    properties: {
      privateDnsZoneConfigs: [ { name: 'blob', properties: { privateDnsZoneId: dnsZone.id } } ]
    }
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${appName}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${appName}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableLocalAuth: true
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${appName}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}

resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  // azd deploys the hook service's code to the app with this tag.
  tags: union(tags, { 'azd-service-name': 'hook' })
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: vnet.properties.subnets[0].id
    siteConfig: { minTlsVersion: '1.2' }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainer}'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      scaleAndConcurrency: { maximumInstanceCount: 40, instanceMemoryMB: 2048 }
      runtime: { name: 'python', version: '3.12' }
    }
  }
  dependsOn: [ blobEndpoint::zoneGroup, dnsZone::link ]

  resource settings 'config' = {
    name: 'appsettings'
    properties: {
      AzureWebJobsStorage__accountName: storage.name
      AzureWebJobsStorage__credential: 'managedidentity'
      APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'Authorization=AAD'
      BLOCKED_TOOLS: blockedTools
    }
  }

  // Easy Auth: validate the bearer token, its audience, and its caller before any function runs.
  resource auth 'config' = {
    name: 'authsettingsV2'
    properties: {
      platform: { enabled: true }
      globalValidation: { requireAuthentication: true, unauthenticatedClientAction: 'Return401' }
      identityProviders: {
        azureActiveDirectory: {
          enabled: true
          registration: {
            clientId: hookClientId
            openIdIssuer: 'https://sts.windows.net/${tenant().tenantId}/v2.0'
          }
          validation: {
            allowedAudiences: [ hookAudience, hookClientId ]
            defaultAuthorizationPolicy: {
              allowedPrincipals: { identities: [ gatewayPrincipalId ] }
            }
          }
        }
      }
      login: { tokenStore: { enabled: false } }
    }
  }
}

resource blobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, app.id, blobDataOwnerRoleId)
  scope: storage
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataOwnerRoleId)
  }
}

resource metricsPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, app.id, metricsPublisherRoleId)
  scope: appInsights
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', metricsPublisherRoleId)
  }
}

output appName string = app.name
output hookHost string = app.properties.defaultHostName
output hookUrl string = 'https://${app.properties.defaultHostName}/api/tool-hook'
output appInsightsName string = appInsights.name
output logWorkspaceName string = logs.name
output logWorkspaceId string = logs.properties.customerId
