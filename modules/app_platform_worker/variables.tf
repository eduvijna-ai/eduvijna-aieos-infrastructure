variable "app_name" {
  type        = string
  description = <<-EOT
    DigitalOcean App Platform application name. Must satisfy the
    ADR-AIEOS-048R1 provider-compliant naming contract (max 32 chars;
    lowercase letter start; lowercase letters/digits/hyphen only;
    letter or digit end).
  EOT

  validation {
    condition = (
      length(var.app_name) >= 2 &&
      length(var.app_name) <= 32 &&
      can(regex("^[a-z][a-z0-9-]*[a-z0-9]$", var.app_name))
    )
    error_message = "app_name must be 2-32 chars, start with a lowercase letter, contain only lowercase letters/digits/hyphens, and end with a lowercase letter or digit."
  }
}

variable "region" {
  type        = string
  description = "App Platform region slug."
}

variable "project_id" {
  type        = string
  description = "Existing DigitalOcean project UUID."
}

variable "vpc_id" {
  type        = string
  description = "Dedicated production VPC UUID."
}

variable "instance_size_slug" {
  type        = string
  description = "Worker instance size slug."
}

variable "instance_count" {
  type        = number
  description = "Worker instance count."
}

variable "image_registry_type" {
  type        = string
  description = "Image registry type. DOCR for the first-production AIEOS path."
}

variable "image_repository" {
  type        = string
  description = "Repository name within the logical account registry."
}

variable "image_digest" {
  type        = string
  description = "Immutable OCI manifest digest."
  nullable    = false

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.image_digest))
    error_message = "image_digest must match ^sha256:[0-9a-f]{64}$."
  }
}

variable "run_command" {
  type        = string
  description = "Exact worker run command."
}
