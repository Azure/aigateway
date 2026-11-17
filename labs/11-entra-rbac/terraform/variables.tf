variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab11-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "principal_id" {
  description = "Object ID of the user, group, service principal, or managed identity to grant. Empty uses the signed-in identity."
  type        = string
  default     = ""

  validation {
    condition     = var.principal_id == "" || can(regex("^[0-9a-fA-F-]{36}$", var.principal_id))
    error_message = "The principal ID must be empty or an object ID (a GUID)."
  }
}

variable "principal_type" {
  description = "Type of that identity: User, Group, or ServicePrincipal (apps and managed identities)."
  type        = string
  default     = "User"

  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.principal_type)
    error_message = "The principal type must be User, Group, or ServicePrincipal."
  }
}

variable "role" {
  description = "Role to grant: user (AI Gateway User), models (AI Gateway Models User), or tools (AI Gateway Tools User)."
  type        = string
  default     = "models"

  validation {
    condition     = contains(["user", "models", "tools"], var.role)
    error_message = "The role must be user, models, or tools."
  }
}

variable "role_scope" {
  description = "Where to grant the role: all assets (workspace, the default workspace), the whole gateway, or only the default alias."
  type        = string
  default     = "workspace"

  validation {
    condition     = contains(["workspace", "gateway", "alias"], var.role_scope)
    error_message = "The role scope must be workspace, gateway, or alias."
  }

  validation {
    condition     = !(var.role == "tools" && var.role_scope == "alias")
    error_message = "AI Gateway Tools User can't be assigned on a model alias."
  }
}
