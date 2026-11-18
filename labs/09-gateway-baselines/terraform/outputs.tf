output "azure_resource_group" {
  value = var.resource_group_name
}

output "ai_gateway_name" {
  value = data.azapi_resource.gateway.name
}

output "ai_gateway_id" {
  value = data.azapi_resource.gateway.id
}

# Every policy at Gateway scope after the apply, including the ones that Terraform doesn't manage.
output "gateway_scope_policies" {
  value = [for p in try(azapi_resource_action.baseline.output.properties.policies, []) : p.type]
}

output "ip_filter_ranges" {
  value = var.remove_baseline ? [] : local.allowed_cidrs
}
