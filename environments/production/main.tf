# Production root module — modeled only.
# All production mutation guards default to false. No apply is authorized by this foundation.

locals {
  app_platform_region           = "blr"
  app_platform_vpc_datacenter   = "blr1"
  app_platform_vpc_required     = true
  app_platform_dedicated_egress = false
  production_vpc_name           = "aieos-prod-blr1"
  production_vpc_region         = "blr1"
  production_vpc_cidr           = "10.130.0.0/20"
  app_platform_instance_size    = "apps-s-1vcpu-1gb-fixed"
  app_platform_instance_count   = 1
  app_registry_type             = "DOCR"
  app_image_repository          = "aieos-backend"

  # Commercial guardrails (list USD, pre-tax, discovered 2026-08-21). Not final full-estate total.
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
  aieos_backend_image_digest_valid = (
    var.aieos_backend_image_digest != null &&
    can(regex("^sha256:[0-9a-f]{64}$", var.aieos_backend_image_digest))
  )
  any_digitalocean_slice_enabled = (
    var.enable_production_vpc ||
    var.enable_aistor_resources ||
    var.enable_workflow_dispatcher_app ||
    var.enable_temporal_worker_app
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
  workflow_dispatcher_app_instances = (
    var.enable_workflow_dispatcher_app &&
    var.enable_production_vpc &&
    local.aieos_backend_image_digest_valid
    ? { production = true }
    : {}
  )
  temporal_worker_app_instances = (
    var.enable_temporal_worker_app &&
    var.enable_production_vpc &&
    local.aieos_backend_image_digest_valid
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

check "workflow_dispatcher_app_requires_production_vpc" {
  assert {
    condition     = !var.enable_workflow_dispatcher_app || var.enable_production_vpc
    error_message = "enable_workflow_dispatcher_app requires enable_production_vpc = true."
  }
}

check "temporal_worker_app_requires_production_vpc" {
  assert {
    condition     = !var.enable_temporal_worker_app || var.enable_production_vpc
    error_message = "enable_temporal_worker_app requires enable_production_vpc = true."
  }
}

check "workflow_dispatcher_app_requires_common_digest" {
  assert {
    condition     = !var.enable_workflow_dispatcher_app || local.aieos_backend_image_digest_valid
    error_message = "enable_workflow_dispatcher_app requires aieos_backend_image_digest to be a non-null immutable sha256 digest."
  }
}

check "temporal_worker_app_requires_common_digest" {
  assert {
    condition     = !var.enable_temporal_worker_app || local.aieos_backend_image_digest_valid
    error_message = "enable_temporal_worker_app requires aieos_backend_image_digest to be a non-null immutable sha256 digest."
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

module "workflow_dispatcher_app" {
  source   = "../../modules/app_platform_worker"
  for_each = local.workflow_dispatcher_app_instances

  app_name            = "eduvijna-aieos-prod-workflow-dispatcher"
  region              = local.app_platform_region
  project_id          = module.production_project[each.key].project_id
  vpc_id              = module.production_vpc[each.key].vpc_id
  instance_size_slug  = local.app_platform_instance_size
  instance_count      = local.app_platform_instance_count
  image_registry_type = local.app_registry_type
  image_repository    = local.app_image_repository
  image_digest        = var.aieos_backend_image_digest
  run_command         = "python -m aieos.platform.runtime.entrypoints.workflow_dispatcher_main"
}

module "temporal_worker_app" {
  source   = "../../modules/app_platform_worker"
  for_each = local.temporal_worker_app_instances

  app_name            = "eduvijna-aieos-prod-temporal-worker"
  region              = local.app_platform_region
  project_id          = module.production_project[each.key].project_id
  vpc_id              = module.production_vpc[each.key].vpc_id
  instance_size_slug  = local.app_platform_instance_size
  instance_count      = local.app_platform_instance_count
  image_registry_type = local.app_registry_type
  image_repository    = local.app_image_repository
  image_digest        = var.aieos_backend_image_digest
  run_command         = "python -m aieos.platform.runtime.entrypoints.temporal_worker_main"
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
