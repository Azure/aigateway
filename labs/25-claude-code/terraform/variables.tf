variable "resource_group_name" {
  description = "Resource group of the existing AI Gateway."
  type        = string
}

variable "gateway_name" {
  description = "Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in that resource group."
  type        = string
}

variable "foundry_account_id" {
  description = "Resource ID of the Foundry account that has the Claude deployments. It can be in another resource group or subscription."
  type        = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.CognitiveServices/accounts/[^/]+$", var.foundry_account_id))
    error_message = "foundry_account_id takes the account's resource ID: /subscriptions/<id>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<name>."
  }
}

variable "claude_models" {
  description = "Claude deployments to publish, each with the tokens per minute that each caller can use through its alias."
  type = list(object({
    name              = string
    tokens_per_minute = number
  }))
  default = [
    { name = "claude-opus-5-5", tokens_per_minute = 100000 },
    { name = "claude-sonnet-5-5", tokens_per_minute = 100000 },
    { name = "claude-haiku-5-5", tokens_per_minute = 100000 },
  ]
}

variable "budget_model" {
  description = "Deployment whose alias also gets a cost limit. Empty adds no cost limit."
  type        = string
  default     = "claude-opus-5-5"
}

variable "budget_amount" {
  description = "Budget for each caller, in US dollars, such as 5 or 0.05."
  type        = number
  default     = 5

  validation {
    condition     = var.budget_amount > 0
    error_message = "budget_amount must be greater than 0."
  }
}

variable "budget_period" {
  description = "Renewal period of the budget. Budgets renew in fixed calendar windows."
  type        = string
  default     = "day"

  validation {
    condition     = contains(["hour", "day", "week", "month", "year"], var.budget_period)
    error_message = "budget_period takes hour, day, week, month, or year."
  }
}

variable "budget_id" {
  description = "ID of the cost limit. Keep it to keep the spend counted so far; change it to start a new count."
  type        = string
  default     = "claude-code-budget"
}

variable "grant_foundry_user" {
  description = "Grant the gateway's managed identity the Foundry User role on the account. Set it to false when the role is already assigned, for example by the portal's import."
  type        = bool
  default     = true
}

variable "create_provider" {
  description = "Create the Foundry provider named after the account. Set it to false when the gateway already has it, for example from the portal's import, so that Terraform keeps its settings, such as its authentication."
  type        = bool
  default     = true
}

variable "api_key_name" {
  description = "Name of the runtime API key to create for Claude Code."
  type        = string
  default     = "claude-code"
}

variable "learn_mcp_server" {
  description = "Publish the public Microsoft Learn MCP server as the MCP server learn, like lab 04's tool-server.bicep."
  type        = bool
  default     = false
}
