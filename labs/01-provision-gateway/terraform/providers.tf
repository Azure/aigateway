# Provider versions are pinned, so every lab plans the same way. AI Gateway resources go through azapi; the
# resource group uses azurerm.
terraform {
  required_version = ">= 1.9"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "2.10.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "5.12.0"
    }
  }
}

# Both providers sign in with your Azure CLI session and use the subscription in ARM_SUBSCRIPTION_ID.
provider "azapi" {}

provider "azurerm" {
  features {
    # Delete the resource group even when it holds resources that you added outside Terraform.
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
