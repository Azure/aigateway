variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab24-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "model_name" {
  description = "Model to deploy and publish for Copilot. The deployment, the backend model, and the alias use this name."
  type        = string
  default     = "gpt-6.1-sol"
}

variable "model_version" {
  description = "Version of that model."
  type        = string
  default     = "2026-09-29"
}

variable "model_sku" {
  description = "Deployment SKU. Use DataZoneStandard if your GlobalStandard quota for the model is used up."
  type        = string
  default     = "GlobalStandard"

  validation {
    condition     = contains(["GlobalStandard", "DataZoneStandard"], var.model_sku)
    error_message = "The model SKU must be GlobalStandard or DataZoneStandard."
  }
}

variable "model_capacity" {
  description = "Deployment capacity in thousands of tokens per minute. Coding agents send large prompts, so give them room."
  type        = number
  default     = 100

  validation {
    condition     = var.model_capacity >= 1 && floor(var.model_capacity) == var.model_capacity
    error_message = "The model capacity must be a whole number of at least 1."
  }
}

variable "tokens_per_minute" {
  description = "Tokens per minute that each caller identity can use on the model through the gateway."
  type        = number
  default     = 100000

  validation {
    condition     = var.tokens_per_minute >= 1000 && floor(var.tokens_per_minute) == var.tokens_per_minute
    error_message = "The token limit must be a whole number of at least 1000."
  }
}
