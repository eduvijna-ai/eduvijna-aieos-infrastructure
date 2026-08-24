# Production root module — modeled only.
# All production mutation guards default to false. No apply is authorized by this foundation.
# ADR-AIEOS-048R2: production App Platform digitalocean_app ownership is REJECTED.
# App lifecycle belongs to the governed state-free deployment plane (WPI-AP-DP01).

locals {
  production_vpc_name   = "aieos-prod-blr1"
  production_vpc_region = "blr1"
  production_vpc_cidr   = "10.130.0.0/20"

  # Commercial guardrails (list USD, pre-tax, discovered 2026-08-21). Not final full-estate total.
  # App workload costs remain architecture/commercial evidence under ADR-AIEOS-048R2 even though
  # OpenTofu no longer owns digitalocean_app resources.
  commercial_retained_usd_mo                = 79.90
  commercial_aistor_node_usd_mo             = 24.00
  commercial_aistor_volumes_usd_mo          = 114.00
  commercial_aistor_slice_usd_mo            = 217.90
  commercial_workflow_dispatcher_app_usd_mo = 10.00
  commercial_temporal_worker_app_usd_mo     = 10.00
  commercial_first_production_subtotal_usd_mo = (
    local.commercial_aistor_slice_usd_mo +
    local.commercial_workflow_dispatcher_app_usd_mo +
    local.commercial_temporal_worker_app_usd_mo
  )
  commercial_optional_registry_sensitivity_usd_mo = (
    local.commercial_first_production_subtotal_usd_mo + 5.00
  )
  commercial_target_usd_mo       = 240.00
  commercial_hard_ceiling_usd_mo = 250.00
  # Statutory taxes including Indian GST are tracked separately and do not
  # consume the USD 250 DigitalOcean service-charge ceiling (ADR-AIEOS-044).
  commercial_gst_basis              = "STATUTORY_TAXES_TRACKED_SEPARATELY"
  commercial_full_estate_incomplete = true

  # OpenTofu DigitalOcean slices after ADR-AIEOS-048R2: VPC + AIStor only.
  any_digitalocean_slice_enabled = (
    var.enable_production_vpc ||
    var.enable_aistor_resources
  )
  production_project_instances = (
    local.any_digitalocean_slice_enabled
    ? { production = true }
    : {}
  )
  production_vpc_instances = (
    var.enable_production_vpc
    ? { production = true }
    : {}
  )
  aistor_resource_instances = (
    var.enable_aistor_resources && var.enable_production_vpc
    ? { production = true }
    : {}
  )

  # WPI-I01R1 — zero provider instances when account ID is null (disabled/inert).
  temporal_cloud_provider_instances = (
    var.temporal_cloud_allowed_account_id == null
    ? {}
    : {
      production = var.temporal_cloud_allowed_account_id
    }
  )

  # Resource instances ⊆ provider instances; fail-closed if enable=true without account ID.
  temporal_cloud_resource_instances = (
    var.enable_temporal_cloud_resources
    ? { production = true }
    : {}
  )
}

check "bootstrap_commercial_slice_under_target" {
  assert {
    condition     = local.commercial_aistor_slice_usd_mo <= local.commercial_target_usd_mo
    error_message = "AIStor-slice estimate exceeds USD 240/month operating target; Chief Architect review required."
  }
}

check "first_production_subtotal_under_target" {
  assert {
    condition     = local.commercial_first_production_subtotal_usd_mo <= local.commercial_target_usd_mo
    error_message = "Modeled first-production subtotal exceeds the USD 240/month operating target; Chief Architect review required."
  }
}

check "first_production_subtotal_under_hard_ceiling" {
  assert {
    condition     = local.commercial_first_production_subtotal_usd_mo <= local.commercial_hard_ceiling_usd_mo
    error_message = "Modeled first-production subtotal exceeds the USD 250/month hard ceiling; fail closed."
  }
}

check "aistor_requires_production_vpc" {
  assert {
    condition     = !var.enable_aistor_resources || var.enable_production_vpc
    error_message = "enable_aistor_resources requires enable_production_vpc = true."
  }
}

module "production_project" {
  source   = "../../modules/production_project"
  for_each = local.production_project_instances

  project_id   = var.do_project_id
  project_name = var.do_project_name
}

module "production_vpc" {
  source   = "../../modules/production_vpc"
  for_each = local.production_vpc_instances

  name     = var.production_vpc_name
  region   = var.production_vpc_region
  ip_range = var.production_vpc_ip_range
  # Explicit collision verification is an operational gate before apply.
}

module "aistor_bootstrap" {
  source   = "../../modules/aistor_bootstrap"
  for_each = local.aistor_resource_instances

  droplet_name   = var.aistor_droplet_name
  region         = var.production_vpc_region
  size           = var.aistor_size
  image          = var.aistor_image
  vpc_uuid       = module.production_vpc[each.key].vpc_id
  project_id     = module.production_project[each.key].project_id
  volume_names   = var.aistor_volume_names
  volume_size_gb = var.aistor_volume_size_gb
  mount_points   = var.aistor_mount_points
  tags           = var.tags
}

module "aistor_network" {
  source   = "../../modules/aistor_network"
  for_each = local.aistor_resource_instances

  name        = "aieos-prod-aistor"
  droplet_ids = [module.aistor_bootstrap[each.key].droplet_id]
  vpc_uuid    = module.production_vpc[each.key].vpc_id
  tags        = var.tags
  # Admin source CIDRs are pre-apply configuration — never hard-code developer/home IPs here.
  admin_source_cidrs = []
  s3_source_cidrs    = [var.production_vpc_ip_range]
}

# Temporal Cloud workflow plane — Namespace + two service accounts only.
# Independent of DigitalOcean slice guards. Default for_each {} (source modeling).
# Does NOT manage API keys (token would enter tfstate — later credential gate).
module "temporal_cloud_workflow_plane" {
  source   = "../../modules/temporal_cloud_workflow_plane"
  for_each = local.temporal_cloud_resource_instances

  providers = {
    temporalcloud = temporalcloud.production[each.key]
  }

  namespace_name           = var.temporal_namespace_name
  namespace_region         = var.temporal_namespace_region
  namespace_retention_days = var.temporal_namespace_retention_days
}
