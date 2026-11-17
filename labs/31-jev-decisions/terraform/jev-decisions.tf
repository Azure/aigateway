# Publishes TypeSafe's Jev decision model on the gateway: a Custom model provider that calls the TypeSafe API with
# your TypeSafe key, the Jev model with the System One endpoint, the ticket-triage alias with a request rate limit for
# each caller, and a runtime API key for the triage app. The TypeSafe key goes in sensitive_body, a write-only
# argument: the gateway stores it, and Terraform never saves it. Read the runtime key with
# az aigateway api-key list-secrets.

# Write-only arguments, such as sensitive_body, need Terraform 1.11 or later.
terraform {
  required_version = ">= 1.11"
}

locals {
  workspace_id = "${module.gateway.gateway_id}/workspaces/default"
}

# 1. A Custom provider for the TypeSafe API. Its one header carries the TypeSafe key on every call to TypeSafe.
resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = "typesafe"
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Custom"
      displayName       = "TypeSafe"
      description       = "TypeSafe Jev decision models."
      custom = {
        endpoint = {
          url = "https://api.typesafe.ai"
        }
      }
    }
  }

  # Merged into the request body, and kept out of the plan and the state. terraform destroy doesn't need the key.
  sensitive_body = var.jev_api_key == null ? null : {
    properties = {
      authentication = {
        headers = [
          {
            name  = "Authorization"
            value = "Bearer ${var.jev_api_key}"
          },
        ]
      }
    }
  }

  schema_validation_enabled = false

  lifecycle {
    precondition {
      condition     = var.jev_api_key != null
      error_message = "Set your TypeSafe key in TF_VAR_jev_api_key before terraform plan."
    }
  }
}

# 2. The Jev model. typesafe/v1/systemone is the System One decisions endpoint, written without a leading slash.
resource "azapi_resource" "model" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = var.jev_model
  parent_id = azapi_resource.provider.id

  body = {
    properties = {
      displayName = var.jev_model
      description = "TypeSafe Jev decision model."
      supportedEndpoints = [
        "typesafe/v1/systemone",
      ]
      deployment = {
        modelName = var.jev_model
      }
    }
  }

  schema_validation_enabled = false
}

# 3. The alias that apps call, with a limit on decision requests per minute for each caller identity.
resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "ticket-triage"
  parent_id = local.workspace_id

  body = {
    properties = {
      aliasName   = "ticket-triage"
      description = "Decision alias for support ticket triage."
      backendModels = [
        {
          resourceId = azapi_resource.model.id
        },
      ]
      policies = var.decisions_per_minute > 0 ? [
        {
          type       = "requestRateLimit"
          count      = var.decisions_per_minute
          period     = "minute"
          counterKey = ["identity"]
        },
      ] : []
    }
  }

  schema_validation_enabled = false
}

# 4. A runtime API key for the triage app. Its value is never an output, so it stays out of the Terraform state.
resource "azapi_resource" "api_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = "app-ticket-triage"
  parent_id = module.gateway.gateway_id

  body = {
    properties = {
      displayName = "app-ticket-triage"
    }
  }

  schema_validation_enabled = false
}
