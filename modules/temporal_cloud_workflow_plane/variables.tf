variable "namespace_name" {
  type        = string
  nullable    = false
  description = "Temporal Cloud Namespace name (provider-compatible lowercase syntax). Required when module instance exists."

  validation {
    condition = (
      length(var.namespace_name) >= 2 &&
      length(var.namespace_name) <= 64 &&
      can(regex("^[a-z][a-z0-9-]*[a-z0-9]$", var.namespace_name))
    )
    error_message = "namespace_name must be 2-64 chars, start with a letter, contain only lowercase letters/digits/hyphens, and not end with a hyphen."
  }
}

variable "namespace_region" {
  type        = string
  nullable    = false
  description = "Exactly one Temporal Cloud region code. Required when module instance exists."

  validation {
    condition     = length(trimspace(var.namespace_region)) > 0
    error_message = "namespace_region must be a non-empty string."
  }
}

variable "namespace_retention_days" {
  type        = number
  nullable    = false
  description = "Namespace retention_days. Required when module instance exists."

  validation {
    condition     = var.namespace_retention_days == floor(var.namespace_retention_days) && var.namespace_retention_days >= 1
    error_message = "namespace_retention_days must be a positive integer."
  }
}
