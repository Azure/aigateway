output "provider_name" {
  value = azapi_resource.provider.name
}

output "model_names" {
  value = [for model in azapi_resource.model : model.name]
}

output "alias_name" {
  value = azapi_resource.alias.name
}

output "alias_id" {
  value = azapi_resource.alias.id
}
