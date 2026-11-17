// Registers the three Microsoft Entra ID applications of the on-behalf-of chain with the Microsoft Graph Bicep
// extension (bicepconfig.json):
//   - <baseName>-mcp-backend: the MCP backend's API. It exposes the delegated scope user_impersonation and is the
//     audience of the tokens that the backend accepts.
//   - <baseName>-token-exchange: the app that the gateway signs in as to exchange the user's token. It exposes
//     FederationApp.Access, pre-authorized for Azure AI Gateway, holds tenant-wide consent for user_impersonation, and
//     trusts the gateway's user-assigned managed identity through a federated credential, so it needs no secret.
//   - <baseName>-copilot-connector: the client that Microsoft 365 Copilot signs users in with. It holds tenant-wide
//     consent for AI Gateway's Data.All scope, and for openid and offline_access, so users get no consent prompt.
// The extension creates or updates each application by its uniqueName and never deletes one: the lab's Clean up does.
// It can't create client secrets, so you add the connector's secret when you connect Microsoft 365 Copilot.
extension microsoftGraphV1

@description('Prefix of the application names.')
param baseName string

@description('Principal (object) ID of the gateway\'s user-assigned managed identity, the subject of the federated credential.')
param gatewayIdentityPrincipalId string

@description('Object ID of the owner of the applications. The default is the user or service principal that deploys.')
param ownerObjectId string = deployer().objectId

var tenantId = tenant().tenantId
var aiGatewayAppId = '18550318-e177-4205-a743-6816d6fcdc3f'
var graphAppId = '00000003-0000-0000-c000-000000000000'
var backendScopeName = 'user_impersonation'
var owners = { relationships: [ ownerObjectId ] }

var backendName = '${baseName}-mcp-backend'
var tokenExchangeName = '${baseName}-token-exchange'
var connectorName = '${baseName}-copilot-connector'
var backendScopeId = guid(tenantId, backendName, backendScopeName)
var federationScopeId = guid(tenantId, tokenExchangeName, 'FederationApp.Access')

// Azure AI Gateway's service principal in your tenant: created when it's missing, left as it is otherwise.
resource aiGatewaySp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: aiGatewayAppId
}

resource graphSp 'Microsoft.Graph/servicePrincipals@v1.0' existing = {
  appId: graphAppId
}

resource backendApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: backendName
  displayName: backendName
  signInAudience: 'AzureADMyOrg'
  owners: owners
  api: {
    // v2 tokens: the audience is the client ID, and the issuer is login.microsoftonline.com/<tenant>/v2.0.
    requestedAccessTokenVersion: 2
    oauth2PermissionScopes: [
      {
        id: backendScopeId
        value: backendScopeName
        type: 'User'
        isEnabled: true
        adminConsentDisplayName: 'Call the MCP backend as the signed-in user'
        adminConsentDescription: 'Allows the AI Gateway token exchange app to call the MCP backend on behalf of the signed-in user.'
        userConsentDisplayName: 'Call the MCP backend as you'
        userConsentDescription: 'Allows the app to call the MCP backend on your behalf.'
      }
    ]
  }
}

resource backendSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: backendApp.appId
  owners: owners
}

resource tokenExchangeApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: tokenExchangeName
  displayName: tokenExchangeName
  signInAudience: 'AzureADMyOrg'
  owners: owners
  api: {
    requestedAccessTokenVersion: 2
    oauth2PermissionScopes: [
      {
        id: federationScopeId
        value: 'FederationApp.Access'
        type: 'User'
        isEnabled: true
        adminConsentDisplayName: 'Exchange user tokens through Azure AI Gateway'
        adminConsentDescription: 'Allows Azure AI Gateway to exchange the signed-in user\'s token through this app.'
        userConsentDisplayName: 'Let Azure AI Gateway act on your behalf'
        userConsentDescription: 'Allows Azure AI Gateway to call backend tools on your behalf.'
      }
    ]
    // Azure AI Gateway can request FederationApp.Access without a consent prompt.
    preAuthorizedApplications: [
      {
        appId: aiGatewaySp.appId
        delegatedPermissionIds: [ federationScopeId ]
      }
    ]
  }
  requiredResourceAccess: [
    {
      resourceAppId: backendApp.appId
      resourceAccess: [
        {
          id: backendScopeId
          type: 'Scope'
        }
      ]
    }
  ]

  // The gateway's user-assigned identity signs in as this app. The subject is the identity's principal ID.
  resource gatewayCredential 'federatedIdentityCredentials@v1.0' = {
    name: '${tokenExchangeApp.uniqueName}/ai-gateway'
    description: 'Azure AI Gateway user-assigned managed identity'
    audiences: [ 'api://AzureADTokenExchange' ]
    issuer: '${environment().authentication.loginEndpoint}${tenantId}/v2.0'
    subject: gatewayIdentityPrincipalId
  }
}

resource tokenExchangeSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: tokenExchangeApp.appId
  owners: owners
}

// The gateway addresses the token exchange app as api://<client ID>. With another URI, tool calls fail with 502.
module backendUri 'app-identifier-uri.bicep' = {
  name: 'aigw-backend-uri'
  params: {
    uniqueName: backendApp.uniqueName
    displayName: backendApp.displayName
    appId: backendApp.appId
  }
}

module tokenExchangeUri 'app-identifier-uri.bicep' = {
  name: 'aigw-token-exchange-uri'
  params: {
    uniqueName: tokenExchangeApp.uniqueName
    displayName: tokenExchangeApp.displayName
    appId: tokenExchangeApp.appId
  }
}

// Tenant-wide admin consent for the exchange: the token exchange app may call the backend as any user.
resource tokenExchangeConsent 'Microsoft.Graph/oauth2PermissionGrants@v1.0' = {
  clientId: tokenExchangeSp.id
  resourceId: backendSp.id
  consentType: 'AllPrincipals'
  scope: backendScopeName
}

var dataAllScopeId = filter(aiGatewaySp.oauth2PermissionScopes, s => s.value == 'Data.All')[0].id
var signInScopes = map(
  filter(graphSp.oauth2PermissionScopes, s => contains([ 'openid', 'offline_access' ], s.value)),
  s => { id: s.id, type: 'Scope' }
)

resource connectorApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: connectorName
  displayName: connectorName
  signInAudience: 'AzureADMyOrg'
  owners: owners
  web: {
    // The redirect URI of OAuth 2.0 connectors in Microsoft 365 Copilot.
    redirectUris: [ 'https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect' ]
  }
  requiredResourceAccess: [
    {
      resourceAppId: aiGatewayAppId
      resourceAccess: [
        {
          id: dataAllScopeId
          type: 'Scope'
        }
      ]
    }
    {
      // openid and offline_access let Microsoft 365 Copilot sign the user in and refresh the token.
      resourceAppId: graphAppId
      resourceAccess: signInScopes
    }
  ]
}

resource connectorSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: connectorApp.appId
  owners: owners
}

resource connectorGatewayConsent 'Microsoft.Graph/oauth2PermissionGrants@v1.0' = {
  clientId: connectorSp.id
  resourceId: aiGatewaySp.id
  consentType: 'AllPrincipals'
  scope: 'Data.All'
}

resource connectorSignInConsent 'Microsoft.Graph/oauth2PermissionGrants@v1.0' = {
  clientId: connectorSp.id
  resourceId: graphSp.id
  consentType: 'AllPrincipals'
  scope: 'openid offline_access'
}

output backendAppId string = backendUri.outputs.appId
output backendScope string = '${backendUri.outputs.identifierUri}/${backendScopeName}'
output tokenExchangeAppId string = tokenExchangeUri.outputs.appId
output connectorAppId string = connectorApp.appId
