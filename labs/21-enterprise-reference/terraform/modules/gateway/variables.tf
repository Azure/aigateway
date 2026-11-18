variable "resource_group_id" {
  description = "Resource ID of the resource group that holds the gateway."
  type        = string
}

variable "location" {
  description = "Region for the gateway. Pick one where AI Gateway is available."
  type        = string
}

variable "gateway_name" {
  description = "Gateway name, max 24 characters. Its first 10 characters start the runtime host name."
  type        = string

  validation {
    condition     = length(var.gateway_name) >= 1 && length(var.gateway_name) <= 24
    error_message = "The gateway name must have 1 to 24 characters."
  }
}

variable "tags" {
  description = "Tags applied to the gateway."
  type        = map(string)
  default     = {}
}

variable "backend_subnet_id" {
  description = "Optional subnet resource ID for outbound virtual network integration. The subnet must be delegated to Microsoft.App/environments."
  type        = string
  default     = ""
}

variable "foundry_resource_ids" {
  description = "Resource IDs of the Foundry accounts the gateway calls with its managed identity."
  type        = list(string)
  default     = []
}
