output "foundation_status" {
  description = "Human-readable foundation posture."
  value = {
    production_vpc_enabled           = var.enable_production_vpc
    aistor_resources_enabled         = var.enable_aistor_resources
    workflow_dispatcher_app_enabled  = var.enable_workflow_dispatcher_app
    temporal_worker_app_enabled      = var.enable_temporal_worker_app
    temporal_cloud_resources_enabled = var.enable_temporal_cloud_resources
    # TRUE = authorized production remote S3 backend initialization gate completed.
    # TRUE does NOT mean remote tfstate exists, apply occurred, or workload resources exist.
    # Production remote tfstate object existence is operational execution evidence and is
    # intentionally not encoded in this state-backed output.
    production_state_initialized = true
    apply_authorized             = false
    app_platform = {
      region              = local.app_platform_region
      vpc_datacenter      = local.app_platform_vpc_datacenter
      vpc_networking      = local.app_platform_vpc_required
      dedicated_egress_ip = local.app_platform_dedicated_egress
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
    app_platform_contract = {
      region                        = local.app_platform_region
      instance_size_slug            = local.app_platform_instance_size
      instance_count                = local.app_platform_instance_count
      image_registry_type           = local.app_registry_type
      image_repository              = local.app_image_repository
      image_digest_set              = var.aieos_backend_image_digest != null
      runtime_env_owned_by_opentofu = false
    }
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
    workflow_dispatcher_app       = length(module.workflow_dispatcher_app)
    temporal_worker_app           = length(module.temporal_worker_app)
    temporal_cloud_workflow_plane = length(module.temporal_cloud_workflow_plane)
  }
}

output "workflow_dispatcher_app" {
  description = "Non-secret App Platform identifiers for the WORKFLOW_DISPATCHER app when enabled; nulls when disabled."
  value = {
    enabled              = var.enable_workflow_dispatcher_app
    app_id               = try(module.workflow_dispatcher_app["production"].app_id, null)
    app_urn              = try(module.workflow_dispatcher_app["production"].app_urn, null)
    active_deployment_id = try(module.workflow_dispatcher_app["production"].active_deployment_id, null)
  }
}

output "temporal_worker_app" {
  description = "Non-secret App Platform identifiers for the TEMPORAL_WORKER app when enabled; nulls when disabled."
  value = {
    enabled              = var.enable_temporal_worker_app
    app_id               = try(module.temporal_worker_app["production"].app_id, null)
    app_urn              = try(module.temporal_worker_app["production"].app_urn, null)
    active_deployment_id = try(module.temporal_worker_app["production"].active_deployment_id, null)
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
