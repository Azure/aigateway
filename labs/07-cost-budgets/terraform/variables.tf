variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab07-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "budget_amount" {
  description = "Default budget for each caller, in US dollars. Decimals such as 0.01 work."
  type        = number
  default     = 5

  validation {
    condition     = var.budget_amount > 0
    error_message = "The budget must be greater than 0."
  }
}

variable "period" {
  description = "Renewal period. Budgets renew in fixed calendar windows: hour, day, week, month, or year."
  type        = string
  default     = "day"

  validation {
    condition     = contains(["hour", "day", "week", "month", "year"], var.period)
    error_message = "The period must be hour, day, week, month, or year."
  }
}

variable "default_key_name" {
  description = "Runtime API key that gets the default budget."
  type        = string
  default     = "app-dev"
}

variable "override_key_name" {
  description = "Runtime API key that gets its own budget."
  type        = string
  default     = "support-bot"
}

variable "override_amount" {
  description = "Budget for the override key, in US dollars."
  type        = number
  default     = 50

  validation {
    condition     = var.override_amount > 0
    error_message = "The override budget must be greater than 0."
  }
}

variable "entra_object_id" {
  description = "Object ID of the Microsoft Entra user or service principal that gets its own budget. Leave it unset for the identity that runs Terraform; an empty string adds no Entra override."
  type        = string
  default     = null
}

variable "entra_amount" {
  description = "Budget for that Microsoft Entra identity, in US dollars."
  type        = number
  default     = 20

  validation {
    condition     = var.entra_amount > 0
    error_message = "The Entra budget must be greater than 0."
  }
}
