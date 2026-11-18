variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the gateway's unique name."
  type        = string
  default     = "aigw-lab31-tf"
}

variable "location" {
  description = "Region for the gateway. Pick one where AI Gateway is available (Setup guide, Find the available regions)."
  type        = string
  default     = "eastus2"
}

# Ephemeral: Terraform reads it from TF_VAR_jev_api_key at plan and apply, and never writes it to the plan or the state.
variable "jev_api_key" {
  description = "Your TypeSafe API key. The gateway sends it to TypeSafe as Authorization: Bearer <key>."
  type        = string
  sensitive   = true
  ephemeral   = true
  default     = null
}

variable "jev_model" {
  description = "A Jev model name that your TypeSafe account can call, such as jev-latest or a pinned version."
  type        = string
  default     = "jev-latest"
}

variable "decisions_per_minute" {
  description = "Decision requests per minute for each caller on the ticket-triage alias, or 0 for no limit."
  type        = number
  default     = 5

  validation {
    condition     = var.decisions_per_minute >= 0 && floor(var.decisions_per_minute) == var.decisions_per_minute
    error_message = "The limit must be a whole number of 0 or more."
  }
}
