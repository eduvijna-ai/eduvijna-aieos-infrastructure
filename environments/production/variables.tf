variable "do_project_id" {
  type        = string
  description = "Existing DigitalOcean project ID for AIEOS production (project name AIEOS). Do not create a second production project."
}

variable "do_project_name" {
  type        = string
  description = "Expected production project name (verification only)."
  default     = "AIEOS"
}

variable "production_vpc_name" {
  type        = string
  description = "Frozen production VPC name from ADR-AIEOS-048. Must not be changed without a later governed source revision."
  default     = "aieos-prod-blr1"

  validation {
    condition     = var.production_vpc_name == "aieos-prod-blr1"
    error_message = "production_vpc_name is architecture-frozen to aieos-prod-blr1."
  }
}

variable "production_vpc_region" {
  type        = string
  description = "Frozen DigitalOcean region slug for the dedicated production VPC and AIStor."
  default     = "blr1"

  validation {
    condition     = var.production_vpc_region == "blr1"
    error_message = "production_vpc_region is architecture-frozen to blr1."
  }
}

variable "production_vpc_ip_range" {
  type        = string
  description = <<-EOT
    Frozen dedicated production VPC CIDR from ADR-AIEOS-048. Collision proof
    against existing account VPCs (including default-blr1 10.122.0.0/20 and
    DOKS cluster/service subnets) remains a pre-apply operational gate, but
    this root must not silently drift away from 10.130.0.0/20.
  EOT
  default     = "10.130.0.0/20"

  validation {
    condition     = var.production_vpc_ip_range == "10.130.0.0/20"
    error_message = "production_vpc_ip_range is architecture-frozen to 10.130.0.0/20."
  }
}

variable "aistor_droplet_name" {
  type    = string
  default = "aieos-prod-aistor-01"
}

variable "aistor_size" {
  type    = string
  default = "s-2vcpu-4gb"
}

variable "aistor_image" {
  type        = string
  description = "Ubuntu 24.04 LTS distribution slug."
  default     = "ubuntu-24-04-x64"
}

variable "aistor_volume_size_gb" {
  type        = number
  description = "Nominal size per AIStor data Volume (GiB)."
  default     = 190
}

variable "aistor_volume_names" {
  type = list(string)
  default = [
    "aieos-prod-aistor-data-01",
    "aieos-prod-aistor-data-02",
    "aieos-prod-aistor-data-03",
    "aieos-prod-aistor-data-04",
    "aieos-prod-aistor-data-05",
    "aieos-prod-aistor-data-06",
  ]

  validation {
    condition     = length(var.aistor_volume_names) == 6
    error_message = "Bootstrap AIStor requires exactly six dedicated Volumes."
  }
}

variable "aistor_mount_points" {
  type = list(string)
  default = [
    "/srv/aistor/data01",
    "/srv/aistor/data02",
    "/srv/aistor/data03",
    "/srv/aistor/data04",
    "/srv/aistor/data05",
    "/srv/aistor/data06",
  ]

  validation {
    condition     = length(var.aistor_mount_points) == 6
    error_message = "Bootstrap AIStor requires exactly six mount points."
  }
}

variable "primary_bucket_name" {
  type        = string
  description = "Intended literal production primary bucket (documentation / later create)."
  default     = "aieos-assets-prod"
}

variable "tags" {
  type        = list(string)
  description = "Common tags for production AIStor resources."
  default = [
    "aieos",
    "production",
    "bootstrap",
    "aistor",
  ]
}

variable "enable_production_vpc" {
  type        = bool
  description = <<-EOT
    Independent production VPC activation guard. Default false = source
    modeling only. No other slice is implicitly enabled by this guard.
  EOT
  default     = false
}

variable "enable_aistor_resources" {
  type        = bool
  description = <<-EOT
    Independent AIStor activation guard. Default false = source modeling only.
    Requires enable_production_vpc = true; does not implicitly enable any other
    production slice.
  EOT
  default     = false
}

variable "enable_temporal_cloud_resources" {
  type        = bool
  description = <<-EOT
    Independent Temporal Cloud activation guard (WPI-I01).
    Default false = source modeling only.
    Setting true requires a later explicit Chief Architect production
    Temporal Cloud provisioning gate. Independent from DigitalOcean VPC / AIStor guards. Does NOT authorize API-key issuance,
    commercial enrollment, plan, or apply by itself.
  EOT
  default     = false
}

variable "temporal_cloud_allowed_account_id" {
  type        = string
  description = <<-EOT
    Temporal Cloud account ID safety guard for the temporalcloud provider
    (allowed_account_id). null = Temporal plane not configured in this
    OpenTofu invocation (NOT a production default). When non-null, instantiates
    a dynamic provider instance. Never commit the live production account ID
    as a source constant.
  EOT
  default     = null
  nullable    = true

  validation {
    condition = (
      var.temporal_cloud_allowed_account_id == null ||
      length(trimspace(var.temporal_cloud_allowed_account_id)) > 0
    )
    error_message = "temporal_cloud_allowed_account_id must be null or a non-empty string."
  }
}

variable "temporal_namespace_name" {
  type        = string
  description = <<-EOT
    Intended Temporal Cloud Namespace name. null = unresolved / not configured
    (NOT a production default). Non-null values must satisfy provider Namespace
    syntax. Unresolved provisioning decision — do not freeze WPI-PF01
    recommendations here.
  EOT
  default     = null
  nullable    = true

  validation {
    condition = var.temporal_namespace_name == null || (
      length(var.temporal_namespace_name) >= 2 &&
      length(var.temporal_namespace_name) <= 64 &&
      can(regex("^[a-z][a-z0-9-]*[a-z0-9]$", var.temporal_namespace_name))
    )
    error_message = "temporal_namespace_name must be null or 2-64 chars, start with a letter, contain only lowercase letters/digits/hyphens, and not end with a hyphen."
  }
}

variable "temporal_namespace_region" {
  type        = string
  description = <<-EOT
    Exactly one Temporal Cloud region code for the production Namespace.
    null = unresolved / not configured (NOT a production default). Non-binding
    leading candidates are documented only in
    docs/WPI-I01-TEMPORAL-CLOUD-PROVISIONING-SOURCE.md — do not treat
    documentation as a frozen value.
  EOT
  default     = null
  nullable    = true

  validation {
    condition = (
      var.temporal_namespace_region == null ||
      length(trimspace(var.temporal_namespace_region)) > 0
    )
    error_message = "temporal_namespace_region must be null or a non-empty string."
  }
}

variable "temporal_namespace_retention_days" {
  type        = number
  description = <<-EOT
    Namespace retention_days. null = unresolved / not configured (NOT a
    production default). Unresolved architecture/provisioning decision — not
    frozen by WPI-I01.
  EOT
  default     = null
  nullable    = true

  validation {
    condition = var.temporal_namespace_retention_days == null || (
      var.temporal_namespace_retention_days == floor(var.temporal_namespace_retention_days) &&
      var.temporal_namespace_retention_days >= 1
    )
    error_message = "temporal_namespace_retention_days must be null or a positive integer."
  }
}
