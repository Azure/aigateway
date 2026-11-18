variable "subscription_id" {
  description = "Subscription that holds the resource group."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for every resource."
  type        = string
}

variable "resource_group_id" {
  description = "Resource ID of the same resource group."
  type        = string
}

variable "location" {
  description = "Region for every resource."
  type        = string
}

variable "tags" {
  description = "Tags for every resource."
  type        = map(string)
  default     = {}
}

variable "gateway_name" {
  description = "Gateway name. It becomes the first label of the runtime host name."
  type        = string

  validation {
    condition     = length(var.gateway_name) <= 24
    error_message = "The gateway name must be 24 characters or fewer."
  }
}

variable "foundry_name" {
  description = "Foundry account name, also its custom subdomain. It must be globally unique."
  type        = string
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

variable "capacity" {
  description = "Deployment capacity in thousands of tokens per minute."
  type        = number
  default     = 10
}

variable "provider_name" {
  description = "Name of the gateway's model provider."
  type        = string
  default     = "foundry-models"
}

variable "api_key_name" {
  description = "Name of the runtime API key."
  type        = string
  default     = "app-first-call"
}
