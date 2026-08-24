output "foundation_status" {
  description = "Human-readable foundation posture."
  value = {
    production_vpc_enabled           = var.enable_production_vpc
    aistor_resources_enabled         = var.enable_aistor_resources
    temporal_cloud_resources_enabled = var.enable_temporal_cloud_resources
    # TRUE = authorized production remote S3 backend initialization gate completed.
    # TRUE does NOT mean remote tfstate exists, apply occurred, or workload resources exist.
    # Production remote tfstate object existence is operational execution evidence and is
    # intentionally not encoded in this state-backed output.
    production_state_initialized = true
    apply_authorized             = false
    app_platform_ownership = {
      opentofu_digitalocean_app_owned = false
      lifecycle_owner                 = "GOVERNED_STATE_FREE_DEPLOYMENT_PLANE"
      architecture_authority          = "ADR-AIEOS-048R2"
    }
    commercial = {
      retained_usd_mo                      = local.commercial_retained_usd_mo
      aistor_node_usd_mo                   = local.commercial_aistor_node_usd_mo
      aistor_volumes_usd_mo                = local.commercial_aistor_volumes_usd_mo
      aistor_slice_usd_mo                  = local.commercial_aistor_slice_usd_mo
      workflow_dispatcher_app_usd_mo       = local.commercial_workflow_dispatcher_app_usd_mo
      temporal_worker_app_usd_mo           = local.commercial_temporal_worker_app_usd_mo
      first_production_subtotal_usd_mo     = local.commercial_first_production_subtotal_usd_mo
      optional_registry_sensitivity_usd_mo = local.commercial_optional_registry_sensitivity_usd_mo
      target_usd_mo                        = local.commercial_target_usd_mo
      hard_ceiling_usd_mo                  = local.commercial_hard_ceiling_usd_mo
      gst_basis                            = local.commercial_gst_basis
      full_estate_incomplete               = local.commercial_full_estate_incomplete
    }
    primary_bucket_intended = var.primary_bucket_name
    vpc_name_intended       = var.production_vpc_name
    vpc_cidr_frozen         = var.production_vpc_ip_range
    legacy_state_bucket     = "eduvijna-terraform-state"
    production_state_bucket = "eduvijna-aieos-tofu-state-prod-sfo3"
  }
}

output "module_instantiation" {
  description = "Whether cloud-mutating modules are currently instantiated."
  value = {
    production_project            = length(module.production_project)
    production_vpc                = length(module.production_vpc)
    aistor_bootstrap              = length(module.aistor_bootstrap)
    aistor_network                = length(module.aistor_network)
    temporal_cloud_workflow_plane = length(module.temporal_cloud_workflow_plane)
  }
}

output "temporal_cloud_workflow_plane" {
  description = "Non-secret Temporal Cloud workflow-plane identifiers when enabled; nulls when guard is false."
  value = {
    enabled                                = var.enable_temporal_cloud_resources
    namespace_id                           = try(module.temporal_cloud_workflow_plane["production"].namespace_id, null)
    namespace_grpc_address                 = try(module.temporal_cloud_workflow_plane["production"].namespace_grpc_address, null)
    workflow_dispatcher_service_account_id = try(module.temporal_cloud_workflow_plane["production"].workflow_dispatcher_service_account_id, null)
    temporal_worker_service_account_id     = try(module.temporal_cloud_workflow_plane["production"].temporal_worker_service_account_id, null)
  }
}
