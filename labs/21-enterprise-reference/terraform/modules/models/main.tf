# Models, like modules/models.bicep: a Foundry provider that signs in with the gateway's managed identity, a
# backend model per deployment with a per-caller token limit and content safety, an alias that apps send in the
# "model" field, and the AI Gateway Models User role on the alias for Microsoft Entra principals.
terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

locals {
  workspace_id                = "${var.gateway_id}/workspaces/default"
  models_user_role_id         = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
  normalized_foundry_endpoint = endswith(var.foundry_endpoint, "/") ? var.foundry_endpoint : "${var.foundry_endpoint}/"
}

resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = var.provider_name
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Foundry"
      displayName       = var.provider_display_name
      description       = var.provider_description
      foundry = {
        endpoint = {
          url = local.normalized_foundry_endpoint
        }
        resourceIds = var.foundry_resource_ids
      }
      authentication = {
        managedIdentity = {
          resource = "https://cognitiveservices.azure.com/"
        }
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "model" {
  for_each  = var.models
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01"
  name      = each.key
  parent_id = azapi_resource.provider.id

  body = {
    properties = {
      description        = each.value.description
      displayName        = each.value.model_name
      supportedEndpoints = each.value.supported_endpoints
      deployment = {
        resourceId   = each.value.resource_id
        modelName    = reverse(split("/", each.value.resource_id))[0]
        modelVersion = each.value.model_version
      }
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = each.value.token_limit
          counterKey = ["identity"]
        },
        {
          type             = "contentSafety"
          hateSeverity     = var.content_safety_severity
          violenceSeverity = var.content_safety_severity
          sexualSeverity   = var.content_safety_severity
          selfHarmSeverity = var.content_safety_severity
        },
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = var.alias_name
  parent_id = local.workspace_id

  body = {
    properties = {
      backendModels = [
        {
          resourceId = azapi_resource.model[var.alias_model].id
        },
      ]
    }
  }

  schema_validation_enabled = false
}

resource "azurerm_role_assignment" "alias_users" {
  for_each                         = { for user in var.alias_users : user.principal_id => user }
  name                             = uuidv5("url", "${azapi_resource.alias.id}/${each.key}/${local.models_user_role_id}")
  scope                            = azapi_resource.alias.id
  role_definition_id               = "/subscriptions/${split("/", var.gateway_id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.models_user_role_id}"
  principal_id                     = each.key
  principal_type                   = each.value.principal_type
  skip_service_principal_aad_check = each.value.principal_type == "ServicePrincipal"
}
