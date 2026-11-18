# The virtual network for the gateway's outbound integration:
#   - an NSG for the integration subnet, with no custom rules: AI Gateway needs no outbound service-tag rules
#   - an integration subnet, delegated to Microsoft.App/environments and dedicated to the gateway
#   - a subnet for private endpoints
#   - with gateway_private_endpoint, a client subnet delegated to Microsoft.ContainerInstance/containerGroups for a
#     test client in the network
resource "azurerm_network_security_group" "integration" {
  name                = "nsg-aigw-integration"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-aigw"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
  address_space       = ["10.20.0.0/16"]
}

# /27 is the minimum for the integration subnet; /24 leaves room to scale.
resource "azurerm_subnet" "integration" {
  name                 = "snet-aigw-integration"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.20.0.0/24"]

  delegation {
    name = "Microsoft.App.environments"
    service_delegation {
      name = "Microsoft.App/environments"
      # Azure adds this action to the delegation. Declaring it keeps the next plan free of changes.
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet_network_security_group_association" "integration" {
  subnet_id                 = azurerm_subnet.integration.id
  network_security_group_id = azurerm_network_security_group.integration.id
}

resource "azurerm_subnet" "private_endpoints" {
  name                              = "snet-private-endpoints"
  resource_group_name               = azurerm_resource_group.rg.name
  virtual_network_name              = azurerm_virtual_network.vnet.name
  address_prefixes                  = ["10.20.1.0/24"]
  private_endpoint_network_policies = "Disabled"
}

# The client subnet exists only with the gateway's private endpoint: a container there tests the private path.
resource "azurerm_subnet" "clients" {
  count                = var.gateway_private_endpoint ? 1 : 0
  name                 = "snet-clients"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.20.2.0/24"]

  delegation {
    name = "Microsoft.ContainerInstance.containerGroups"
    service_delegation {
      name    = "Microsoft.ContainerInstance/containerGroups"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}
