variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab14-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "client_app_metrics" {
  description = "Export the client app claims, appid and azp, to metrics too. false keeps the recommended preset: logs and traces only."
  type        = bool
  default     = true
}

variable "principal_id" {
  description = "Object ID of the identity that calls the gateway with Entra tokens. Empty means the identity that runs Terraform."
  type        = string
  default     = ""
}

variable "principal_type" {
  description = "Type of that identity: User, Group, or ServicePrincipal."
  type        = string
  default     = "User"

  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.principal_type)
    error_message = "principal_type must be User, Group, or ServicePrincipal."
  }
}
