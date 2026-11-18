# Provider versions are pinned, so every lab plans the same way. AI Gateway resources, the image build, and the
# container app's built-in authentication go through azapi; the resource group, identities, logs, registry, and
# Container Apps use azurerm. This lab adds two providers: azuread registers the three applications of the
# on-behalf-of chain in Microsoft Entra ID (the Bicep track uses the Microsoft Graph Bicep extension), and time waits
# for new directory objects and role assignments to replicate.
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
    time = {
      source  = "hashicorp/time"
      version = "0.14.2"
    }
  }
}

# The providers sign in with your Azure CLI session; azapi and azurerm use the subscription in ARM_SUBSCRIPTION_ID,
# and azuread uses the session's tenant.
provider "azapi" {}

provider "azurerm" {
  features {
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
