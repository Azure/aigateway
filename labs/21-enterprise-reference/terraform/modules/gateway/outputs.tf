output "name" {
  value = azapi_resource.gateway.name
}

output "id" {
  value = azapi_resource.gateway.id
}

# try() keeps terraform import working: an imported resource has no output until the next refresh.
output "hostname" {
  value = try(azapi_resource.gateway.output.properties.frontend.defaultHostname, "")
}

output "url" {
  value = "https://${try(azapi_resource.gateway.output.properties.frontend.defaultHostname, "")}"
}

output "principal_id" {
  value = azapi_resource.gateway.identity[0].principal_id
}
