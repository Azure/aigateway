output "gateway_name" {
  value = azapi_resource.gateway.name
}

output "gateway_id" {
  value = azapi_resource.gateway.id
}

output "gateway_url" {
  # try() keeps terraform import working: an imported resource has no output until the next refresh.
  value = "https://${try(azapi_resource.gateway.output.properties.frontend.defaultHostname, "")}"
}

output "principal_id" {
  value = azapi_resource.gateway.identity[0].principal_id
}
