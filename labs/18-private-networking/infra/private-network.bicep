// Private routing for a new AI Gateway (Microsoft.ApiManagement/aigateways).
// Outbound virtual network integration can only be set when the gateway is created, so this template creates:
//   - an NSG that allows outbound TCP 443 to the Storage and AzureKeyVault service tags
//   - a virtual network with an integration subnet (delegated to Microsoft.App/environments, dedicated to the
//     gateway) and a private-endpoint subnet
//   - the gateway, joined to the integration subnet, by reusing the lab 01 template as a module
//   - optionally, a private endpoint to a Foundry resource (group ID "account") with its private DNS zones
// Inbound private endpoints and disabling the gateway's public network access aren't available for the
// aigateways resource type yet, so the template doesn't declare them.
// The lab's main.bicep calls it with azd. You can also deploy it on its own to an existing resource group with
// "az deployment group create".

@description('Name of the new gateway, 24 characters or fewer. It becomes the first label of the runtime host name.')
@minLength(1)
@maxLength(24)
param gatewayName string

@description('Region for the gateway and the network. Pick one where AI Gateway is available. The integration subnet must be in the gateway region.')
param location string = 'eastus2'

@description('Tags applied to the gateway and the network resources.')
param tags object = {}

@description('Name of the virtual network.')
param vnetName string = 'vnet-aigw'

@description('Address space of the virtual network.')
param vnetAddressPrefix string = '10.20.0.0/16'

@description('Name of the subnet dedicated to the gateway\'s outbound integration.')
param integrationSubnetName string = 'snet-aigw-integration'

@description('Prefix of the integration subnet. /27 is the minimum; /24 leaves room to scale.')
param integrationSubnetPrefix string = '10.20.0.0/24'

@description('Name of the subnet that holds private endpoints to backends.')
param privateEndpointSubnetName string = 'snet-private-endpoints'

@description('Prefix of the private-endpoint subnet.')
param privateEndpointSubnetPrefix string = '10.20.1.0/24'

@description('Name of the network security group attached to the integration subnet.')
param nsgName string = 'nsg-aigw-integration'

@description('Optional resource ID of a Foundry (AIServices) account to reach privately. Leave empty to skip.')
param foundryAccountId string = ''

@description('Name of the private endpoint to the Foundry account.')
param foundryPrivateEndpointName string = 'pe-foundry-${gatewayName}'

var includeFoundryPrivateEndpoint = !empty(foundryAccountId)

// Standard private DNS zones for Foundry (AIServices) accounts.
var foundryDnsZoneNames = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
]

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: nsgName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowStorageOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Storage'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowKeyVaultOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureKeyVault'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

// Subnets are declared inline so that redeploying the template never tries to delete them.
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [ vnetAddressPrefix ]
    }
    subnets: [
      {
        name: integrationSubnetName
        properties: {
          addressPrefix: integrationSubnetPrefix
          networkSecurityGroup: {
            id: nsg.id
          }
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource integrationSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnet
  name: integrationSubnetName
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnet
  name: privateEndpointSubnetName
}

// The gateway, created with private routing through the integration subnet (lab 01's template).
module gateway '../../01-provision-gateway/infra/gateway.bicep' = {
  name: 'aigw-${gatewayName}'
  params: {
    gatewayName: gatewayName
    location: location
    tags: tags
    backendSubnetId: integrationSubnet.id
  }
}

// Outbound: the integrated gateway resolves the Foundry account to a private IP and calls it privately.
resource foundryDnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zoneName in foundryDnsZoneNames: if (includeFoundryPrivateEndpoint) {
  name: zoneName
  location: 'global'
  tags: tags
}]

resource foundryDnsZoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in foundryDnsZoneNames: if (includeFoundryPrivateEndpoint) {
  parent: foundryDnsZones[i]
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}]

resource foundryPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (includeFoundryPrivateEndpoint) {
  name: foundryPrivateEndpointName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'foundry'
        properties: {
          privateLinkServiceId: foundryAccountId
          groupIds: [ 'account' ]
        }
      }
    ]
  }
}

resource foundryPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (includeFoundryPrivateEndpoint) {
  parent: foundryPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (zoneName, i) in foundryDnsZoneNames: {
      name: replace(zoneName, '.', '-')
      properties: {
        privateDnsZoneId: foundryDnsZones[i].id
      }
    }]
  }
}

output vnetId string = vnet.id
output integrationSubnetId string = integrationSubnet.id
output privateEndpointSubnetId string = privateEndpointSubnet.id
output gatewayName string = gateway.outputs.gatewayName
output gatewayId string = gateway.outputs.gatewayId
output gatewayUrl string = gateway.outputs.gatewayUrl
output principalId string = gateway.outputs.principalId
output foundryPrivateEndpointName string = includeFoundryPrivateEndpoint ? foundryPrivateEndpoint.name : ''
