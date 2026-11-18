# One runtime API key for each caller in api_key_names. Each key is a separate caller identity in metrics and logs,
# and the gateway generates its primary and secondary values, so they never reach the Terraform state. Rotation and
# suspension are operations, not configuration: terraform apply keeps each key's values and state. Removing a name
# from the list deletes that key.
resource "azapi_resource" "api_keys" {
  for_each = toset(var.api_key_names)

  type      = "Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01"
  name      = each.key
  parent_id = module.base.gateway_id

  body = {
    properties = {
      # Keep the display name the same as the key's name, which the CLI and the scripts use.
      displayName = each.key
    }
  }

  schema_validation_enabled = false
}
