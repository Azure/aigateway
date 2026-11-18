variable "resource_group_name" {
  description = "Name of the resource group that holds the monitoring resources."
  type        = string
}

variable "resource_group_id" {
  description = "Resource ID of the same resource group."
  type        = string
}

variable "location" {
  description = "Region for the monitoring resources."
  type        = string
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}

variable "workspace_name" {
  description = "Log Analytics workspace name. It stores the gateway telemetry that Application Insights ingests."
  type        = string
}

variable "app_insights_name" {
  description = "Application Insights component name. The AI Gateway portal suggests <gateway>-insights."
  type        = string
}

variable "retention_in_days" {
  description = "Days to keep data in the Log Analytics workspace."
  type        = number
  default     = 30

  validation {
    condition     = var.retention_in_days >= 30 && var.retention_in_days <= 730
    error_message = "The retention must be 30 to 730 days."
  }
}
