output "api_key_names" {
  value = [for app in var.app_names : azapi_resource.api_key[app].name]
}
