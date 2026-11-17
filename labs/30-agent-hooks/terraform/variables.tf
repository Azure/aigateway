variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab30-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and Flex Consumption are available (az functionapp list-flexconsumption-locations)."
  type        = string
  default     = "eastus2"
}

variable "hook_mode" {
  description = "What the gateway does when the decision service can't answer: failClosed blocks the call, failOpen lets it through."
  type        = string
  default     = "failClosed"

  validation {
    condition     = contains(["failClosed", "failOpen"], var.hook_mode)
    error_message = "hook_mode takes failClosed or failOpen."
  }
}

variable "blocked_tools" {
  description = "Comma-separated tool name patterns that the decision service denies before the call."
  type        = string
  default     = "*code_sample*"
}
