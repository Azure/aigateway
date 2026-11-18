# Lab 18 with Terraform: creates the resource group rg-<environment_name> with a dedicated Foundry account and
# gpt-5-mini (foundry.tf), a virtual network (network.tf), a new gateway with private routing through the network's
# integration subnet, a private endpoint and private DNS for Foundry (foundry-private-endpoint.tf), and lab 02's
# provider, model, private-chat alias, and runtime key (publish-model.tf).
# Pass -var foundry_public_network_access=Disabled to turn off Foundry's public access, and
# -var gateway_private_endpoint=true to add an inbound private endpoint to the gateway (gateway-private-endpoint.tf).
# The key value is never an output.
data "azapi_client_config" "current" {}

locals {
  suffix       = substr(sha1("${data.azapi_client_config.current.subscription_id}/${var.environment_name}/${var.location}"), 0, 6)
  tags         = { "environment-name" = var.environment_name }
  gateway_name = "aigw-${local.suffix}"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.environment_name}"
  location = var.location
  tags     = local.tags
}

# Lab 01's module: the gateway, created with private routing through the integration subnet.
module "gateway" {
  source = "../../01-provision-gateway/terraform/gateway"

  gateway_name      = local.gateway_name
  resource_group_id = azurerm_resource_group.rg.id
  location          = var.location
  tags              = local.tags
  backend_subnet_id = azurerm_subnet.integration.id

  # The integration subnet gets its network security group before the gateway joins it.
  depends_on = [azurerm_subnet_network_security_group_association.integration]
}
