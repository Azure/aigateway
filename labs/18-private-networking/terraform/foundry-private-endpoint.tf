# Outbound: the integrated gateway resolves the Foundry account to a private IP and calls it privately. A private
# endpoint to the account (group ID "account") in the private-endpoint subnet, and the standard private DNS zones
# for Foundry, each linked to the virtual network.
locals {
  foundry_dns_zone_names = [
    "privatelink.cognitiveservices.azure.com",
    "privatelink.openai.azure.com",
    "privatelink.services.ai.azure.com",
  ]
}

resource "azurerm_private_dns_zone" "foundry" {
  for_each            = toset(local.foundry_dns_zone_names)
  name                = each.value
  resource_group_name = azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "foundry" {
  for_each            = azurerm_private_dns_zone.foundry
  name                = "${azurerm_virtual_network.vnet.name}-link"
  private_dns_zone_id = each.value.id
  virtual_network_id  = azurerm_virtual_network.vnet.id
  tags                = local.tags
}

resource "azurerm_private_endpoint" "foundry" {
  name                = "pe-foundry-${local.gateway_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "foundry"
    private_connection_resource_id = azurerm_cognitive_account.foundry.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  # The zone group adds the account's A records to the private DNS zones.
  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [for zone in local.foundry_dns_zone_names : azurerm_private_dns_zone.foundry[zone].id]
  }
}
