# The Foundry account, like modules/foundry.bicep: local auth off, so only Microsoft Entra identities can call it,
# its model deployments, and, when principal_id is set, data-plane roles for a developer.
terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

data "azurerm_client_config" "current" {}

locals {
  # Cognitive Services Contributor, Cognitive Services OpenAI User, and Cognitive Services User
  developer_role_ids = var.principal_id == "" ? [] : [
    "25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68",
    "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
    "a97b65f3-24c7-4388-baec-2e87135dc908",
  ]
}

resource "azurerm_cognitive_account" "foundry" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = lower(var.name)
  local_auth_enabled            = false
  project_management_enabled    = false
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }

  network_acls {
    default_action = "Allow"
  }
}

resource "azurerm_cognitive_deployment" "model" {
  for_each             = var.model_deployments
  name                 = each.key
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  sku {
    name     = each.value.sku_name
    capacity = each.value.capacity
  }

  model {
    format  = each.value.model_format
    name    = each.value.model_name
    version = each.value.model_version
  }
}

resource "azurerm_role_assignment" "developer" {
  for_each           = toset(local.developer_role_ids)
  name               = uuidv5("url", "${azurerm_cognitive_account.foundry.id}/${each.value}/${var.principal_id}")
  scope              = azurerm_cognitive_account.foundry.id
  role_definition_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${each.value}"
  principal_id       = var.principal_id
  principal_type     = "User"
}
