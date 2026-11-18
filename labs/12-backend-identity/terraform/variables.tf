variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab12-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "identity_name" {
  description = "Name of the user-assigned managed identity."
  type        = string
  default     = "id-aigateway-backends"
}

variable "use_user_assigned_identity" {
  description = "Point the Foundry provider at the user-assigned identity. False uses the gateway's system-assigned identity."
  type        = bool
  default     = false
}
