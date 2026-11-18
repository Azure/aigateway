variable "resource_group_name" {
  description = "Resource group of the gateway, where the destination goes."
  type        = string
}

variable "resource_group_id" {
  description = "Resource ID of that resource group."
  type        = string
}

variable "location" {
  description = "Region for the Log Analytics workspace and the Application Insights component."
  type        = string
}

variable "tags" {
  description = "Tags applied to the monitoring resources."
  type        = map(string)
  default     = {}
}

variable "gateway_name" {
  description = "Name of the gateway. The destination is named after it: <gateway>-logs and <gateway>-insights."
  type        = string
}

variable "gateway_principal_id" {
  description = "Object ID of the gateway's system-assigned managed identity, which signs the telemetry export."
  type        = string
}

variable "workspace_id" {
  description = "Resource ID of the gateway's default workspace, the parent of the telemetry exporter."
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
    claim   = string
    signals = list(string)
  }))
  default = [
    { claim = "tid", signals = ["logs", "traces", "metrics"] },
    { claim = "oid", signals = ["logs", "traces", "metrics"] },
    { claim = "appid", signals = ["logs", "traces"] },
    { claim = "azp", signals = ["logs", "traces"] },
  ]

  validation {
    condition     = alltrue([for a in var.claim_attributes : length(a.signals) > 0 && alltrue([for s in a.signals : contains(["logs", "traces", "metrics"], s)])])
    error_message = "Each claim needs at least one signal: logs, traces, or metrics."
  }
}

variable "payload_capture" {
  description = "Log request and response payloads. Off by default: prompts and responses can be sensitive and add volume."
  type        = bool
  default     = false
}
