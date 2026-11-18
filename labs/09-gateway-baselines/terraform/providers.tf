# The provider version is pinned, so the lab plans the same way every time. Gateway scope policies are a property
# of the gateway's default workspace, an AI Gateway resource, so this lab needs only azapi.
terraform {
  required_version = ">= 1.9"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "2.10.0"
    }
  }
}

# The provider signs in with your Azure CLI session and uses the subscription in ARM_SUBSCRIPTION_ID.
provider "azapi" {}
