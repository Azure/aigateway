# The settings of an environment. dev.tfvars and prod.tfvars set the ones that differ, like main.bicepparam and
# prod.bicepparam do for Bicep; the rest keep these defaults.
variable "environment_name" {
  description = "Environment name, for example aigw-dev-tf. Names the resource groups rg-<environment_name>-gateway and rg-<environment_name>-foundrymodels, and seeds the unique resource names."
  type        = string
  default     = "aigw-lab21-tf"

  validation {
    condition     = can(regex("^[a-zA-Z0-9-]{1,64}$", var.environment_name))
    error_message = "The environment name takes 1 to 64 letters, digits, and hyphens."
  }
}

variable "location" {
  description = "Region for the resource groups, the Foundry account, and the monitoring resources. The model and SKU must be available here."
  type        = string
  default     = "eastus2"
}

variable "ai_gateway_location" {
  description = "Region for the gateway. Leave empty to use location. Pick one where AI Gateway is available."
  type        = string
  default     = ""
}

variable "principal_id" {
  description = "Optional Microsoft Entra object ID of a developer, who gets data-plane roles on the Foundry account, the alias, and the MCP server. Leave empty in production."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Extra tags merged into the default tags on every resource group and resource."
  type        = map(string)
  default     = {}
}

variable "ai_gateway_name" {
  description = "Gateway name, max 24 characters. Leave empty for aigw-<suffix>. Its first 10 characters start the runtime host name."
  type        = string
  default     = ""

  validation {
    condition     = var.ai_gateway_name == "" || can(regex("^[a-zA-Z][a-zA-Z0-9-]{0,23}$", var.ai_gateway_name))
    error_message = "The gateway name takes up to 24 letters, digits, and hyphens, and starts with a letter."
  }
}

variable "model_name" {
  description = "Foundry model name to deploy."
  type        = string
  default     = "gpt-5-mini"
}

variable "model_version" {
  description = "Foundry model version to deploy."
  type        = string
  default     = "2025-08-07"
}

variable "model_deployment_name" {
  description = "Name of the Foundry deployment. It's also the backend model name in the gateway."
  type        = string
  default     = "gpt-mini-latest"
}

variable "model_format" {
  description = "Model format for the Foundry deployment."
  type        = string
  default     = "OpenAI"
}

variable "model_sku_name" {
  description = "Model deployment SKU name."
  type        = string
  default     = "GlobalStandard"
}

variable "model_capacity" {
  description = "Deployment capacity, in thousands of tokens per minute for Global Standard."
  type        = number
  default     = 50

  validation {
    condition     = var.model_capacity >= 1
    error_message = "The model capacity must be at least 1."
  }
}

variable "tokens_per_minute_per_caller" {
  description = "Tokens per minute that each caller identity (API key or Microsoft Entra principal) can use on the backend model."
  type        = number
  default     = 20000

  validation {
    condition     = var.tokens_per_minute_per_caller >= 1
    error_message = "The token limit must be at least 1."
  }
}

variable "content_safety_severity" {
  description = "Content safety threshold for every category on the backend model: the lowest severity that is blocked. Low is strictest, None turns the category off."
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

variable "app_names" {
  description = "Apps that get their own runtime API key. Each key is named after the app."
  type        = list(string)
  default     = ["web-chat", "batch-jobs"]
}

variable "model_users" {
  description = "Microsoft Entra principals (usually groups) that get the AI Gateway Models User role on the alias."
  type = list(object({
    principal_id   = string
    principal_type = string
  }))
  default = []

  validation {
    condition     = alltrue([for p in var.model_users : contains(["User", "Group", "ServicePrincipal"], p.principal_type)])
    error_message = "The principal type must be User, Group, or ServicePrincipal."
  }
}

variable "tool_users" {
  description = "Microsoft Entra principals (usually groups) that get the AI Gateway Tools User role on the Microsoft Learn MCP server."
  type = list(object({
    principal_id   = string
    principal_type = string
  }))
  default = []

  validation {
    condition     = alltrue([for p in var.tool_users : contains(["User", "Group", "ServicePrincipal"], p.principal_type)])
    error_message = "The principal type must be User, Group, or ServicePrincipal."
  }
}

variable "log_retention_in_days" {
  description = "Days to keep gateway telemetry in Log Analytics."
  type        = number
  default     = 30

  validation {
    condition     = var.log_retention_in_days >= 30 && var.log_retention_in_days <= 730
    error_message = "The retention must be 30 to 730 days."
  }
}
