variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab18-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "foundry_public_network_access" {
  description = "Public network access of the lab's Foundry account. Set it to Disabled once the private endpoint exists."
  type        = string
  default     = "Enabled"

  validation {
    condition     = contains(["Enabled", "Disabled"], var.foundry_public_network_access)
    error_message = "Public network access must be Enabled or Disabled."
  }
}

variable "gateway_private_endpoint" {
  description = "Add an inbound private endpoint to the gateway, its private DNS zone, and a client subnet."
  type        = bool
  default     = false
}
