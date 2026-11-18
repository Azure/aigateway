variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab02-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "tokens_per_minute" {
  description = "Tokens per minute that each caller identity can use on the model."
  type        = number
  default     = 10000

  validation {
    condition     = var.tokens_per_minute >= 1
    error_message = "The token limit must be at least 1."
  }
}
