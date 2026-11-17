variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab28-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "large_model_name" {
  description = "Higher-quality model to deploy in Foundry. It must be a model that Model Router supports."
  type        = string
  default     = "gpt-5.5"
}

variable "large_model_version" {
  description = "Version of the higher-quality model."
  type        = string
  default     = "2026-04-24"
}

variable "objective" {
  description = "What Model Router favors: Balanced, Cost, or Quality."
  type        = string
  default     = "Balanced"

  validation {
    condition     = contains(["Balanced", "Cost", "Quality"], var.objective)
    error_message = "The objective must be Balanced, Cost, or Quality."
  }
}

variable "allowed_request_overrides" {
  description = "What callers may override per request: objective, model, both, or none. The two filter values turn on the portal's compatibility filters, which aren't caller fields."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for o in var.allowed_request_overrides : contains(["model", "objective", "filterModelsForToolCompatibility", "filterModelsForParameterCompatibility"], o)])
    error_message = "The overrides take model, objective, filterModelsForToolCompatibility, or filterModelsForParameterCompatibility."
  }
}
