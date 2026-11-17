variable "gateway_id" {
  description = "Resource ID of the gateway."
  type        = string
}

variable "provider_name" {
  description = "Name of the model provider to create."
  type        = string
  default     = "foundry"
}

variable "provider_display_name" {
  description = "Display name of the model provider."
  type        = string
  default     = "Foundry"
}

variable "provider_description" {
  description = "Description of the model provider."
  type        = string
  default     = null
}

variable "foundry_endpoint" {
  description = "Endpoint of the Foundry account, for example https://<foundry-account-name>.cognitiveservices.azure.com/."
  type        = string
}

variable "foundry_resource_ids" {
  description = "Resource IDs of the Foundry accounts behind the provider."
  type        = list(string)
}

variable "models" {
  description = "Backend models, keyed by name: the Foundry deployment's resource ID, the model name and version, the per-caller token limit, and the supported endpoints."
  type = map(object({
    description         = string
    resource_id         = string
    model_name          = string
    model_version       = string
    token_limit         = number
    supported_endpoints = list(string)
  }))
}

variable "content_safety_severity" {
  description = "Content safety threshold for every category on every backend model: the lowest severity that is blocked."
  type        = string
  default     = "Medium"

  validation {
    condition     = contains(["None", "Low", "Medium", "High"], var.content_safety_severity)
    error_message = "The severity must be None, Low, Medium, or High."
  }
}

variable "alias_name" {
  description = "Client-facing alias that apps send in the request \"model\" field."
  type        = string
  default     = "chat"
}

variable "alias_model" {
  description = "Key in models of the backend model that the alias points to."
  type        = string
}

variable "alias_users" {
  description = "Microsoft Entra principals that get the AI Gateway Models User role on the alias."
  type = list(object({
    principal_id   = string
    principal_type = string
  }))
  default = []
}
