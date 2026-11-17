variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab03-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

# Ephemeral and sensitive: Terraform passes the key to the provider's write-only sensitive_body, and never writes it
# to the state, the saved plan, or the output.
variable "anthropic_api_key" {
  description = "The Anthropic API key that the gateway sends to Anthropic in the x-api-key header."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "fast_model" {
  description = "A fast model that your Anthropic key can call."
  type        = string
  default     = "claude-haiku-5-5"
}

variable "smart_model" {
  description = "A bigger model that your Anthropic key can call."
  type        = string
  default     = "claude-sonnet-5-5"
}

variable "support_chat_model" {
  description = "The backend model behind support-chat: empty for fast_model, or smart_model."
  type        = string
  default     = ""

  validation {
    condition     = contains(["", var.fast_model, var.smart_model], var.support_chat_model)
    error_message = "support_chat_model takes an empty string, fast_model, or smart_model."
  }
}

variable "support_chat_tokens_per_minute" {
  description = "Per-caller tokens per minute for support-chat."
  type        = number
  default     = 20000

  validation {
    condition     = var.support_chat_tokens_per_minute >= 1
    error_message = "The token limit must be at least 1."
  }
}

variable "batch_chat_tokens_per_minute" {
  description = "Per-caller tokens per minute for batch-chat."
  type        = number
  default     = 2000

  validation {
    condition     = var.batch_chat_tokens_per_minute >= 1
    error_message = "The token limit must be at least 1."
  }
}
