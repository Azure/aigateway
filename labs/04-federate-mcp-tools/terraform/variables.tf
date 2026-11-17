variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the gateway's unique name."
  type        = string
  default     = "aigw-lab04-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway is available (Setup guide, Find the available regions)."
  type        = string
  default     = "eastus2"
}

variable "second_namespace" {
  description = "Namespace for a second, optional Learn backend, such as docs. Empty registers one backend."
  type        = string
  default     = ""
}

variable "supported_versions" {
  description = "MCP protocol versions that clients can negotiate, such as [\"2025-06-18\"]. Every backend must support each one. Empty keeps the server's current list, or the legacy defaults on a new server."
  type        = list(string)
  default     = []
}
