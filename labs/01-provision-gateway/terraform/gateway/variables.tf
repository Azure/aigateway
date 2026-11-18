variable "gateway_name" {
  description = "Gateway name. It becomes the first label of the runtime host name, so use letters, numbers, and hyphens."
  type        = string

  validation {
    condition     = length(var.gateway_name) >= 1 && length(var.gateway_name) <= 24
    error_message = "The gateway name must have 1 to 24 characters."
  }
}

variable "resource_group_id" {
  description = "Resource ID of the resource group that holds the gateway."
  type        = string
}

variable "location" {
  description = "Region for the gateway. Pick one where AI Gateway is available."
  type        = string
}

variable "tags" {
  description = "Tags applied to the gateway."
  type        = map(string)
  default     = {}
}

variable "backend_subnet_id" {
  description = "Optional delegated subnet resource ID for outbound virtual network integration."
  type        = string
  default     = ""
}
