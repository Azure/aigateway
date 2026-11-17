# Provider versions are pinned, so every lab plans the same way. AI Gateway resources go through azapi; the
# resource group, the Foundry account, its model deployments, and role assignments use azurerm.
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
    # Like azd down --purge: purge the Foundry account, so that you can deploy the lab again with the same name.
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
    # Like azd down --purge: delete Log Analytics workspaces permanently, so that you can deploy the lab again.
    log_analytics_workspace {
      permanently_delete_on_destroy = true
    }
    # Delete the resource group even when it holds resources that you added outside Terraform.
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
