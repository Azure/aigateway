variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab17-tf"
}

variable "location" {
  description = "Region for the gateway. Pick one where AI Gateway is available."
  type        = string
  default     = "eastus2"
}

variable "foundry_account_id" {
  description = "Resource ID of the source's Foundry account, the one that the APIM backend foundry-ai-endpoint calls."
  type        = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.CognitiveServices/accounts/[^/]+$", var.foundry_account_id))
    error_message = "Pass the full resource ID of a Microsoft.CognitiveServices/accounts resource."
  }
}

variable "deployment_name" {
  description = "Deployment that the source's model API serves, and the name of the model and alias on the gateway."
  type        = string
  default     = "gpt-5-mini"
}

variable "model_version" {
  description = "Version of the deployed model, from the plan's deploymentConfig."
  type        = string
  default     = "2025-08-07"
}

variable "tokens_per_minute" {
  description = "Tokens per minute for each caller, from the source's llm-token-limit policy."
  type        = number
  default     = 5000

  validation {
    condition     = var.tokens_per_minute >= 1
    error_message = "The token limit must be at least 1."
  }
}
