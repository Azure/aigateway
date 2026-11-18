variable "gateway_id" {
  description = "Resource ID of the gateway."
  type        = string
}

variable "gateway_hostname" {
  description = "Runtime host name of the gateway, for the MCP endpoint output."
  type        = string
}

variable "server_name" {
  description = "MCP server name. It becomes part of the endpoint URL and can't be changed after creation."
  type        = string
  default     = "learn"
}

variable "display_name" {
  description = "Display name shown in the portal catalog."
  type        = string
  default     = "Microsoft Learn"
}

variable "server_description" {
  description = "Description that helps people and agents understand what the tools do."
  type        = string
  default     = "Search and fetch official Microsoft documentation and code samples."
}

variable "namespace" {
  description = "Namespace prefix for the backend's tools."
  type        = string
  default     = "learn"
}

variable "mcp_url" {
  description = "URL of the backend MCP server (Streamable HTTP)."
  type        = string
  default     = "https://learn.microsoft.com/api/mcp"
}

variable "tool_users" {
  description = "Microsoft Entra principals that get the AI Gateway Tools User role on this MCP server."
  type = list(object({
    principal_id   = string
    principal_type = string
  }))
  default = []
}
