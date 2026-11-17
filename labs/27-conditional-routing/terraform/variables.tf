variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab27-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

variable "research_model_name" {
  description = "Research model to deploy in Foundry and route to. The deployment and the backend model use this name."
  type        = string
  default     = "gpt-6.1-sol"
}

variable "research_model_version" {
  description = "Version of the research model."
  type        = string
  default     = "2026-09-29"
}

variable "routing_mode" {
  description = "conditions: x-workload: research requests go to the research model, the rest to gpt-5-mini. affinity: both models share the traffic, and each session stays on one of them."
  type        = string
  default     = "conditions"

  validation {
    condition     = contains(["conditions", "affinity"], var.routing_mode)
    error_message = "The routing mode must be conditions or affinity."
  }
}

variable "research_condition" {
  description = "Conditions mode: the CEL expression that includes the research model for a request. It must return a Boolean."
  type        = string
  default     = "@cel('x-workload' in request.headers && request.headers['x-workload'][0] == 'research')"
}

variable "session_key" {
  description = "Affinity mode: the CEL expression that returns the session key. An empty string means no affinity for the request."
  type        = string
  default     = "@cel('session-id' in request.headers ? request.headers['session-id'][0] : '')"
}
