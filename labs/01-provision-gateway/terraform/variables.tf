variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the gateway's unique name."
  type        = string
  default     = "aigw-lab01-tf"
}

variable "location" {
  description = "Region for the gateway. Pick one where AI Gateway is available (Setup guide, Find the available regions)."
  type        = string
  default     = "eastus2"
}
