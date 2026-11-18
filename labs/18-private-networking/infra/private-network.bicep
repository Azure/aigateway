// Outbound virtual network integration for an AI Gateway (Microsoft.ApiManagement/aigateways). This template creates:
//   - an NSG for the integration subnet, with no custom rules: AI Gateway needs no outbound service-tag rules
//   - a virtual network with an integration subnet (delegated to Microsoft.App/environments, dedicated to the
//     gateway) and a private-endpoint subnet
//   - the gateway, joined to the integration subnet, by reusing the lab 01 template as a module
//   - optionally, a private endpoint to a Foundry resource (group ID "account") with its private DNS zones
//   - optionally, an inbound private endpoint to the gateway (group ID "Gateway") with its private DNS zone, and a
//     client subnet delegated to Microsoft.ContainerInstance/containerGroups for a test client in the network
// The subnet isn't fixed at creation: redeploy with a different backendSubnetId to change it, or use the portal,
// "az aigateway network update", or a REST PATCH to add, change, or remove it on an existing gateway.
// The inbound private endpoint needs private endpoint access for the subscription, so it's off by default: set
// gatewayPrivateEndpoint to true once the subscription has access.
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

@description('Create an inbound private endpoint to the gateway in the private-endpoint subnet, with its private DNS zone, and a client subnet. Needs private endpoint access for the subscription.')
param gatewayPrivateEndpoint bool = false

@description('Name of the inbound private endpoint to the gateway.')
param gatewayPrivateEndpointName string = 'pe-gateway-${gatewayName}'

@description('Name of the subnet for test clients, delegated to Microsoft.ContainerInstance/containerGroups.')
param clientSubnetName string = 'snet-clients'

@description('Prefix of the client subnet.')
param clientSubnetPrefix string = '10.20.2.0/24'

var includeFoundryPrivateEndpoint = !empty(foundryAccountId)

// The client subnet exists only with the gateway's private endpoint: a container there tests the private path.
var clientSubnets = gatewayPrivateEndpoint ? [
  {
    name: clientSubnetName
    properties: {
      addressPrefix: clientSubnetPrefix
      delegations: [
        {
          name: 'Microsoft.ContainerInstance.containerGroups'
          properties: {
            serviceName: 'Microsoft.ContainerInstance/containerGroups'
          }
        }
      ]
    }
  }
] : []

// Standard private DNS zones for Foundry (AIServices) accounts.
var foundryDnsZoneNames = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
]

// The default NSG rules are enough: the gateway reaches backends over TCP 443 inside the virtual network.
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: nsgName
  location: location
  tags: tags
  properties: {
    securityRules: []
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
    subnets: concat([
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
    ], clientSubnets)
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

// Inbound: clients in the virtual network resolve the gateway's host name to a private IP and call it privately.
module gatewayPrivateEndpointDeployment 'gateway-private-endpoint.bicep' = if (gatewayPrivateEndpoint) {
  name: 'aigw-pe-${gatewayName}'
  params: {
    gatewayId: gateway.outputs.gatewayId
    gatewayHostName: replace(gateway.outputs.gatewayUrl, 'https://', '')
    subnetId: privateEndpointSubnet.id
    vnetId: vnet.id
    privateEndpointName: gatewayPrivateEndpointName
    location: location
    tags: tags
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
output gatewayPrivateEndpointName string = gatewayPrivateEndpointDeployment.?outputs.privateEndpointName ?? ''
output gatewayPrivateDnsZone string = gatewayPrivateEndpointDeployment.?outputs.dnsZoneName ?? ''
output clientSubnetId string = gatewayPrivateEndpoint ? '${vnet.id}/subnets/${clientSubnetName}' : ''
