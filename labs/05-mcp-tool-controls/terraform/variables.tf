variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the gateway's unique name."
  type        = string
  default     = "aigw-lab05-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway is available (Setup guide, Find the available regions)."
  type        = string
  default     = "eastus2"
}

variable "allowed_tools" {
  description = "Tool names or patterns to publish. * matches any number of characters and ? exactly one. [\"*\"] publishes every tool."
  type        = list(string)
  default     = ["*_search"]
}

variable "blocked_tools" {
  description = "Tool names or patterns that the gateway refuses to run. They take precedence over allowed_tools."
  type        = list(string)
  default     = ["*code_sample*"]
}

variable "server_access" {
  description = "MCP server access: active, or blocked to stop all client traffic without deleting the server."
  type        = string
  default     = "active"

  validation {
    condition     = contains(["active", "blocked"], var.server_access)
    error_message = "The server access must be active or blocked."
  }
}

variable "calls_per_period" {
  description = "Calls that each counter allows per period. 0 removes the request rate limit."
  type        = number
  default     = 5

  validation {
    condition     = var.calls_per_period >= 0
    error_message = "The calls per period must be 0 or more."
  }
}

variable "period_seconds" {
  description = "Renewal period in seconds, from 1 to 300. The portal offers 30, 60, 120, and 300."
  type        = number
  default     = 30

  validation {
    condition     = var.period_seconds >= 1 && var.period_seconds <= 300
    error_message = "The period must be from 1 to 300 seconds."
  }
}

variable "counter_key" {
  description = "What gets its own counter: [\"identity\"], [\"ipAddress\"], both, or [] for one counter that all callers share."
  type        = list(string)
  default     = ["identity"]

  validation {
    condition     = alltrue([for k in var.counter_key : contains(["identity", "ipAddress"], k)])
    error_message = "The counter key takes identity, ipAddress, both, or none."
  }
}
