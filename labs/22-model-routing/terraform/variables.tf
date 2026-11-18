variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab22-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "candidate_model_name" {
  description = "Candidate model to deploy in Foundry and route to. The deployment and the backend model use this name."
  type        = string
  default     = "gpt-6.1-sol"
}

variable "candidate_model_version" {
  description = "Version of the candidate model."
  type        = string
  default     = "2026-09-29"
}

variable "strategy" {
  description = "weighted: both models share priority 0 and split traffic by weight. priority: gpt-5-mini is preferred."
  type        = string
  default     = "weighted"

  validation {
    condition     = contains(["weighted", "priority"], var.strategy)
    error_message = "The strategy must be weighted or priority."
  }
}

variable "candidate_weight" {
  description = "Weighted strategy only: the candidate weight. gpt-5-mini gets 100 minus this value."
  type        = number
  default     = 20

  validation {
    condition     = var.candidate_weight >= 1 && var.candidate_weight <= 99 && floor(var.candidate_weight) == var.candidate_weight
    error_message = "The candidate weight must be a whole number from 1 to 99."
  }
}
