variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab32-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway, Foundry Agent Service, and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "principal_id" {
  description = "Object ID of the identity that uses the Foundry project. It gets Foundry User on the app team's Foundry resource. Leave it unset for the identity that runs Terraform."
  type        = string
  default     = null
}

variable "principal_type" {
  description = "Type of that identity: User, Group, or ServicePrincipal."
  type        = string
  default     = "User"

  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.principal_type)
    error_message = "The principal type must be User, Group, or ServicePrincipal."
  }
}

variable "project_name" {
  description = "Name of the app team's Foundry project."
  type        = string
  default     = "app-team"
}

variable "use_responses_api" {
  description = "Send the project's requests to the gateway's Responses API, like Use the Responses API for upstream requests in the portal. When false, the gateway receives Chat Completions requests."
  type        = bool
  default     = true
}
