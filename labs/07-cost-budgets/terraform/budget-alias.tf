# Publishes an alias with a cost limit for the quick start's model, creates the app-dev and support-bot runtime API
# keys, and gives support-bot, and optionally one Microsoft Entra identity, a budget of its own with overrides. The
# alias points at the same backend model as the default alias, so only callers that send the new alias name are
# budgeted. Key values are never outputs: read them with az aigateway api-key list-secrets.

# Each key is a separate caller identity, so each one gets its own budget counter.
resource "azapi_resource" "default_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = var.default_key_name
  parent_id = module.base.gateway_id

  body = {
    properties = {
      displayName = var.default_key_name
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "override_key" {
  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = var.override_key_name
  parent_id = module.base.gateway_id

  body = {
    properties = {
      displayName = var.override_key_name
    }
  }

  schema_validation_enabled = false
}

locals {
  alias_name = "${module.base.model_name}-budget"

  # Your own object ID unless you pass another one; an empty string adds no Entra override.
  entra_object_id = var.entra_object_id == null ? data.azapi_client_config.current.object_id : var.entra_object_id

  # Overrides are evaluated in order, and the first match wins. An API key override matches the key's resource ID.
  # An Entra override matches validated token claims, as name and value pairs that must all match: here the tenant
  # ID and the object ID of one identity.
  key_overrides = [
    {
      apiKeyResourceId = azapi_resource.override_key.id
      amount           = var.override_amount
    }
  ]
  entra_overrides = local.entra_object_id == "" ? [] : [
    {
      claims = [
        { name = "tid", value = data.azapi_client_config.current.tenant_id },
        { name = "oid", value = local.entra_object_id },
      ]
      amount = var.entra_amount
    }
  ]
}

resource "azapi_resource" "budget_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = local.alias_name
  parent_id = module.base.workspace_id

  body = {
    properties = {
      aliasName = local.alias_name
      backendModels = [
        { resourceId = module.base.model_id }
      ]
      policies = [
        {
          type = "costLimit"
          # A stable ID: changing the amount on a later apply keeps the spend accumulated so far.
          id     = uuidv5("url", "${module.base.gateway_id}/${local.alias_name}/costLimit")
          amount = var.budget_amount
          period = var.period
          # Overrides need per-caller counters, so the configuration always counts by caller identity.
          counterKey = ["identity"]
          overrides  = concat(local.key_overrides, local.entra_overrides)
        }
      ]
    }
  }

  schema_validation_enabled = false
  depends_on                = [azapi_resource.default_key]
}
