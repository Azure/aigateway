variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab33-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and Azure Container Apps are available."
  type        = string
  default     = "eastus2"
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

variable "mcp_server_source" {
  description = "Git build context of the MCP server image: <repository>.git#<branch>:<folder>."
  type        = string
  default     = "https://github.com/Azure/aigateway.git#main:labs/33-copilot-obo-mcp/infra/mcp-server"
}
