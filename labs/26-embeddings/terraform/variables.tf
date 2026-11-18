variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab26-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway, gpt-5-mini, and text-embedding-3-small are available."
  type        = string
  default     = "eastus2"
}

variable "embeddings_tokens_per_minute" {
  description = "Tokens per minute that each caller identity can send to the embedding model."
  type        = number
  default     = 2000

  validation {
    condition     = var.embeddings_tokens_per_minute >= 1
    error_message = "The token limit must be at least 1."
  }
}
