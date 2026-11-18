variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab13-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "payload_capture" {
  description = "Log request and response payloads. Off by default: prompts and responses can be sensitive and add volume."
  type        = bool
  default     = false
}
