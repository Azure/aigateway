variable "resource_group_name" {
  description = "Name of the resource group that holds the Foundry account."
  type        = string
}

variable "location" {
  description = "Region for the Foundry account. The models and SKUs you deploy must be available here."
  type        = string
}

variable "tags" {
  description = "Tags applied to the account."
  type        = map(string)
  default     = {}
}

variable "name" {
  description = "Foundry account name. It's also the custom subdomain, so it must be globally unique."
  type        = string
}

variable "principal_id" {
  description = "Optional Microsoft Entra object ID of a developer who gets data-plane access to the account. Leave empty in production."
  type        = string
  default     = ""
}

variable "model_deployments" {
  description = "Model deployments, keyed by deployment name."
  type = map(object({
    model_name    = string
    model_format  = string
    model_version = string
    sku_name      = string
    capacity      = number
  }))
}
