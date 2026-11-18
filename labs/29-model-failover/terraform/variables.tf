variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab29-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the gpt-5-mini and backup models are available."
  type        = string
  default     = "eastus2"
}

variable "backup_model_name" {
  description = "Backup model to deploy in Foundry. The deployment and the backend model use the same name."
  type        = string
  default     = "gpt-6.1-sol"
}

variable "backup_model_version" {
  description = "Version of the backup model."
  type        = string
  default     = "2026-09-29"
}

variable "failover" {
  description = "off: the alias only prefers the primary by priority. on: it also fails over to the backup on 429."
  type        = string
  default     = "off"

  validation {
    condition     = contains(["off", "on"], var.failover)
    error_message = "failover takes off or on."
  }
}

variable "exclude_for" {
  description = "How long a throttled backend stays out of the alias, as an ISO 8601 duration up to P1D. Empty: only for the current request."
  type        = string
  default     = "PT30S"
}
