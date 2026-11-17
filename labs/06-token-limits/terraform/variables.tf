variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab06-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "token_limit" {
  description = "Tokens allowed per period for each caller."
  type        = number
  default     = 1000

  validation {
    condition     = var.token_limit >= 1
    error_message = "The token limit must be at least 1."
  }
}

variable "token_limit_period" {
  description = "Token limit window: minute, hour, or day."
  type        = string
  default     = "minute"

  validation {
    condition     = contains(["minute", "hour", "day"], var.token_limit_period)
    error_message = "The period must be minute, hour, or day."
  }
}

variable "token_limit_counter_key" {
  description = "Who gets a token counter: identity (each API key or Entra principal), ipAddress (each client IP address), or both."
  type        = list(string)
  default     = ["identity"]

  validation {
    condition     = length(var.token_limit_counter_key) > 0 && alltrue([for k in var.token_limit_counter_key : contains(["identity", "ipAddress"], k)])
    error_message = "The counter key takes identity, ipAddress, or both."
  }
}
