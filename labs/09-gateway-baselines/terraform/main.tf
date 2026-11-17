# Lab 09 with Terraform: applies the policy baseline in ../infra/baseline-policies.json at Gateway scope on an
# existing gateway, the same file that the Policy as code scripts apply (baseline.tf). Terraform creates no
# Azure resources: it reads the gateway and its default workspace, where Gateway scope policies live.
data "azapi_client_config" "current" {}

data "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/aigateways@2026-11-01"
  name      = var.gateway_name
  parent_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
}

# The current Gateway scope policies, so that removing the baseline keeps every other policy.
data "azapi_resource" "workspace" {
  type                   = "Microsoft.ApiManagement/aigateways/workspaces@2026-11-01"
  name                   = "default"
  parent_id              = data.azapi_resource.gateway.id
  response_export_values = ["properties.policies"]
}

locals {
  allowed_cidrs = [for c in split(",", var.allowed_cidrs) : trimspace(c) if trimspace(c) != ""]

  # The file holds a placeholder address for the IP filter. Never apply it: replace it with allowed_cidrs.
  baseline = [
    for p in jsondecode(file(coalesce(var.baseline_file, "${path.module}/../infra/baseline-policies.json"))) :
    merge(p, { for k in(p.type == "ipFilter" ? ["cidrRanges"] : []) : k => local.allowed_cidrs })
  ]
  baseline_types = [for p in local.baseline : p.type]

  # The Gateway scope policies whose type isn't in the baseline. The service can omit properties.policies when the
  # gateway has no Gateway scope policies, so try() returns an empty list then.
  other_policies = try([
    for p in data.azapi_resource.workspace.output.properties.policies : p if !contains(local.baseline_types, p.type)
  ], [])
}
