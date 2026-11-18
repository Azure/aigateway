variable "environment_name" {
  description = "Names the resource group rg-<environment_name> and seeds the unique resource names."
  type        = string
  default     = "aigw-lab08-tf"
}

variable "location" {
  description = "Region for every resource. Pick one where AI Gateway and the lab's Foundry models are available."
  type        = string
  default     = "eastus2"
}

# The lowest severity that gets blocked: Low (Strict), Medium (Balanced), High (Lenient), or None (Off).
variable "hate_severity" {
  description = "Threshold for the Hate category: Low, Medium, High, or None."
  type        = string
  default     = "Medium"

  validation {
    condition     = contains(["Low", "Medium", "High", "None"], var.hate_severity)
    error_message = "The threshold must be Low, Medium, High, or None."
  }
}

variable "self_harm_severity" {
  description = "Threshold for the Self-harm category: Low, Medium, High, or None."
  type        = string
  default     = "Medium"

  validation {
    condition     = contains(["Low", "Medium", "High", "None"], var.self_harm_severity)
    error_message = "The threshold must be Low, Medium, High, or None."
  }
}

variable "sexual_severity" {
  description = "Threshold for the Sexual category: Low, Medium, High, or None."
  type        = string
  default     = "Medium"

  validation {
    condition     = contains(["Low", "Medium", "High", "None"], var.sexual_severity)
    error_message = "The threshold must be Low, Medium, High, or None."
  }
}

variable "violence_severity" {
  description = "Threshold for the Violence category: Low, Medium, High, or None."
  type        = string
  default     = "Low"

  validation {
    condition     = contains(["Low", "Medium", "High", "None"], var.violence_severity)
    error_message = "The threshold must be Low, Medium, High, or None."
  }
}
