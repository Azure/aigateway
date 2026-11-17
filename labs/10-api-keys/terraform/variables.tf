variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab10-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "api_key_names" {
  description = "Runtime API key names, one for each caller. Names must be unique, ignoring case."
  type        = list(string)
  default     = ["app-dev", "support-bot", "old-notebook"]

  validation {
    condition     = alltrue([for n in var.api_key_names : length(trimspace(n)) > 0])
    error_message = "Key names can't be empty."
  }

  validation {
    condition     = length(distinct([for n in var.api_key_names : lower(n)])) == length(var.api_key_names)
    error_message = "Key names must be unique, ignoring case."
  }
}
