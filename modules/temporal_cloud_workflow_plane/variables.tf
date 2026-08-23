variable "namespace_name" {
  type        = string
  description = "Temporal Cloud Namespace name (provider-compatible lowercase syntax). Production value is an unresolved provisioning decision — not frozen here."

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
  description = "Exactly one Temporal Cloud region code. Production region is unresolved — not frozen here. See docs/WPI-I01-TEMPORAL-CLOUD-PROVISIONING-SOURCE.md for non-binding candidates."

  validation {
    condition     = length(trimspace(var.namespace_region)) > 0
    error_message = "namespace_region must be a non-empty string."
  }
}

variable "namespace_retention_days" {
  type        = number
  description = "Namespace retention_days. Production retention is an unresolved architecture/provisioning decision — not frozen here."

  validation {
    condition     = var.namespace_retention_days == floor(var.namespace_retention_days) && var.namespace_retention_days >= 1
    error_message = "namespace_retention_days must be a positive integer."
  }
}
