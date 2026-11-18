# The baseline at Gateway scope. The default workspace accepts PATCH but not PUT, so Terraform sends the same PATCH
# as the Policy as code scripts: every current Gateway scope policy whose type isn't in the policy file, followed by
# the baseline. Other policies, such as a cost limit, stay. Terraform sends the PATCH again whenever that array
# changes. It doesn't read the policies back, so to undo an edit made in the portal or with the Azure CLI, run
# terraform apply -replace=azapi_resource_action.baseline.
#
# Destroying this resource changes nothing on the gateway. To remove the baseline, apply with
# -var remove_baseline=true first: the PATCH then keeps only the other policies.
resource "azapi_resource_action" "baseline" {
  type        = "Microsoft.ApiManagement/aigateways/workspaces@2026-11-01"
  resource_id = data.azapi_resource.workspace.id
  method      = "PATCH"

  body = {
    properties = {
      # jsonencode() lets the two arrays differ in length and shape.
      policies = jsondecode(var.remove_baseline ? jsonencode(local.other_policies) : jsonencode(flatten([local.other_policies, local.baseline])))
    }
  }

  response_export_values = ["properties.policies"]
}
