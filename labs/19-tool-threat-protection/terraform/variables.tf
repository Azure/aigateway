variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the gateway's unique name."
  type        = string
  default     = "aigw-lab19-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway is available (Setup guide, Find the available regions)."
  type        = string
  default     = "eastus2"
}

variable "pre_invocation" {
  description = "Evaluate each tool request, the tool name and arguments, before the tool runs."
  type        = bool
  default     = false
}

variable "post_invocation" {
  description = "Evaluate each tool result after the tool returns. The tool has already run."
  type        = bool
  default     = false
}

variable "principal_id" {
  description = "Object ID of the user who gets AI Gateway Tools User on the MCP server. Empty uses the signed-in user."
  type        = string
  default     = ""

  validation {
    condition     = var.principal_id == "" || can(regex("^[0-9a-fA-F-]{36}$", var.principal_id))
    error_message = "The principal ID must be empty or a user's object ID (a GUID)."
  }
}
