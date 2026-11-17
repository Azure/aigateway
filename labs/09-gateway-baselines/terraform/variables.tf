variable "resource_group_name" {
  description = "Resource group of the existing gateway that gets the baseline."
  type        = string
}

variable "gateway_name" {
  description = "Name of the existing gateway that gets the baseline."
  type        = string
}

variable "allowed_cidrs" {
  description = "Comma-separated CIDR ranges that the IP filter allows, for example \"198.51.100.7/32\". They replace the placeholder in the policy file."
  type        = string
  default     = ""

  validation {
    condition = var.remove_baseline || (
      length([for c in split(",", var.allowed_cidrs) : c if trimspace(c) != ""]) > 0 &&
      alltrue([for c in split(",", var.allowed_cidrs) : can(cidrhost(trimspace(c), 0)) if trimspace(c) != ""])
    )
    error_message = "Set allowed_cidrs to comma-separated ranges in CIDR notation, for example \"198.51.100.7/32\" for a single address."
  }
}

variable "baseline_file" {
  description = "Policy file to apply. Leave it unset for ../infra/baseline-policies.json, the file that the scripts apply."
  type        = string
  default     = null
}

variable "remove_baseline" {
  description = "Set to true to remove the policy types listed in the policy file from Gateway scope, and keep every other policy."
  type        = bool
  default     = false
}
