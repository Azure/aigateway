# Inbound, with gateway_private_endpoint: clients in the virtual network resolve the gateway's usual host name to a
# private IP and call it privately. A private endpoint to the gateway (group ID "Gateway") in the private-endpoint
# subnet, and the gateway's private DNS zone, linked to the virtual network. The zone follows the gateway's host name:
# a gateway at <name>-<hash>.eastus2-01.ai.gateway.azure.com uses privatelink.eastus2-01.ai.gateway.azure.com.
# AI Gateway approves the connection automatically.
locals {
  gateway_host_name     = trimprefix(module.gateway.gateway_url, "https://")
  gateway_dns_zone_name = "privatelink.${join(".", slice(split(".", local.gateway_host_name), 1, length(split(".", local.gateway_host_name))))}"
}

resource "azurerm_private_dns_zone" "gateway" {
  count               = var.gateway_private_endpoint ? 1 : 0
  name                = local.gateway_dns_zone_name
  resource_group_name = azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "gateway" {
  count               = var.gateway_private_endpoint ? 1 : 0
  name                = "${azurerm_virtual_network.vnet.name}-link"
  private_dns_zone_id = azurerm_private_dns_zone.gateway[0].id
  virtual_network_id  = azurerm_virtual_network.vnet.id
  tags                = local.tags
}

resource "azurerm_private_endpoint" "gateway" {
  count               = var.gateway_private_endpoint ? 1 : 0
  name                = "pe-gateway-${local.gateway_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "gateway"
    private_connection_resource_id = module.gateway.gateway_id
    subresource_names              = ["Gateway"]
    is_manual_connection           = false
  }

  # The zone group adds the gateway's A record to its private DNS zone.
  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.gateway[0].id]
  }
}
