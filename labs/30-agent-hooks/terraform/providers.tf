# Provider versions are pinned, so every lab plans the same way. AI Gateway resources go through azapi; the
# resource group, the decision service's network, storage, logs, plan, and role assignments use azurerm. This lab
# adds two providers: azuread registers the hook's application in Microsoft Entra ID (the Bicep track uses the
# Microsoft Graph Bicep extension), and archive zips the function code in infra/hook for the deployment.
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
    azuread = {
      source  = "hashicorp/azuread"
      version = "3.10.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "2.8.1"
    }
  }
}

# The providers sign in with your Azure CLI session; azapi and azurerm use the subscription in ARM_SUBSCRIPTION_ID,
# and azuread uses the session's tenant.
provider "azapi" {}

provider "azurerm" {
  features {
    # Like azd down --purge: purge the Foundry account, so that you can deploy the lab again with the same name.
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
    # Delete the resource group even when it holds resources that you added outside Terraform.
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
    # Like azd down --purge: delete Log Analytics workspaces permanently, so that you can deploy the lab again.
    log_analytics_workspace {
      permanently_delete_on_destroy = true
    }
  }
}

provider "azuread" {}
