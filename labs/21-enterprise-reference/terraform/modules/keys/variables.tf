variable "gateway_id" {
  description = "Resource ID of the gateway."
  type        = string
}

variable "app_names" {
  description = "One runtime API key is created per entry, named after the app, for example web-chat."
  type        = list(string)
  default     = []
}
