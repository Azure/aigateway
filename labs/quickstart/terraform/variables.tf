variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-quickstart-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the Foundry model are available."
  type        = string
  default     = "eastus2"
}

variable "model_name" {
  description = "Model to deploy in Foundry. The deployment, the gateway model, and the alias use this name."
  type        = string
  default     = "gpt-5-mini"
}

variable "model_version" {
  description = "Version of the model to deploy."
  type        = string
  default     = "2025-08-07"
}
