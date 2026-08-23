variable "enable_temporal_cloud_resources" {
  type    = bool
  default = false
}

variable "temporal_cloud_allowed_account_id" {
  type     = string
  default  = null
  nullable = true
}

variable "temporal_namespace_name" {
  type     = string
  default  = null
  nullable = true
}

variable "temporal_namespace_region" {
  type     = string
  default  = null
  nullable = true
}

variable "temporal_namespace_retention_days" {
  type     = number
  default  = null
  nullable = true
}
