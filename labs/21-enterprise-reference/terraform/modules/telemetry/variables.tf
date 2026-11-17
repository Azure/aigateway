variable "gateway_id" {
  description = "Resource ID of the gateway."
  type        = string
}

variable "gateway_principal_id" {
  description = "Principal ID of the gateway's system-assigned managed identity."
  type        = string
}

variable "app_insights_id" {
  description = "Resource ID of the Application Insights component, with OTLP ingestion on."
  type        = string
}

variable "exporter_name" {
  description = "Name of the telemetry exporter. The portal names it appinsights."
  type        = string
  default     = "appinsights"
}

variable "claim_attributes" {
  description = "Token claims to add to the telemetry, and the signals that carry each one. The default is the portal's \"Include recommended token claims in telemetry\"."
  type = list(object({
    source  = object({ kind = string, value = string })
    signals = list(string)
  }))
  default = [
    { source = { kind = "claims", value = "tid" }, signals = ["logs", "traces", "metrics"] },
    { source = { kind = "claims", value = "oid" }, signals = ["logs", "traces", "metrics"] },
    { source = { kind = "claims", value = "appid" }, signals = ["logs", "traces"] },
    { source = { kind = "claims", value = "azp" }, signals = ["logs", "traces"] },
  ]
}
