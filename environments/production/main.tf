# Production root module — modeled only.
# enable_cloud_resources defaults to false. No apply is authorized by this foundation.

locals {
  app_platform_region           = "blr"
  app_platform_vpc_datacenter   = "blr1"
  app_platform_vpc_required     = true
  app_platform_dedicated_egress = false

  # Commercial guardrails (list USD, pre-tax, discovered 2026-08-21). Not final full-estate total.
  commercial_retained_usd_mo       = 79.90
  commercial_aistor_node_usd_mo    = 24.00
  commercial_aistor_volumes_usd_mo = 114.00
  commercial_aistor_slice_usd_mo   = 217.90
  commercial_target_usd_mo         = 240.00
  commercial_hard_ceiling_usd_mo   = 250.00
  # Statutory taxes including Indian GST are tracked separately and do not
  # consume the USD 250 DigitalOcean service-charge ceiling (ADR-AIEOS-044).
  commercial_gst_basis              = "STATUTORY_TAXES_TRACKED_SEPARATELY"
  commercial_full_estate_incomplete = true

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

module "production_project" {
  source = "../../modules/production_project"
  count  = var.enable_cloud_resources ? 1 : 0

  project_id   = var.do_project_id
  project_name = var.do_project_name
}

module "production_vpc" {
  source = "../../modules/production_vpc"
  count  = var.enable_cloud_resources ? 1 : 0

  name     = var.vpc_name
  region   = var.vpc_region
  ip_range = var.vpc_ip_range
  # Explicit collision verification is an operational gate before apply.
}

module "aistor_bootstrap" {
  source = "../../modules/aistor_bootstrap"
  count  = var.enable_cloud_resources ? 1 : 0

  droplet_name   = var.aistor_droplet_name
  region         = var.vpc_region
  size           = var.aistor_size
  image          = var.aistor_image
  vpc_uuid       = module.production_vpc[0].vpc_id
  project_id     = module.production_project[0].project_id
  volume_names   = var.aistor_volume_names
  volume_size_gb = var.aistor_volume_size_gb
  mount_points   = var.aistor_mount_points
  tags           = var.tags
}

module "aistor_network" {
  source = "../../modules/aistor_network"
  count  = var.enable_cloud_resources ? 1 : 0

  name        = "aieos-prod-aistor"
  droplet_ids = [module.aistor_bootstrap[0].droplet_id]
  vpc_uuid    = module.production_vpc[0].vpc_id
  tags        = var.tags
  # Admin source CIDRs are pre-apply configuration — never hard-code developer/home IPs here.
  admin_source_cidrs = []
  s3_source_cidrs    = [var.vpc_ip_range]
}

# Temporal Cloud workflow plane — Namespace + two service accounts only.
# Independent of enable_cloud_resources. Default for_each {} (source modeling).
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
