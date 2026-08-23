# Disposable NON_PRODUCTION fixture — disabled Temporal provider inertness plan proof.
# No backend.tf — no production remote state. Not authorized for apply.

locals {
  temporal_cloud_provider_instances = (
    var.temporal_cloud_allowed_account_id == null
    ? {}
    : {
      production = var.temporal_cloud_allowed_account_id
    }
  )

  temporal_cloud_resource_instances = (
    var.enable_temporal_cloud_resources
    ? { production = true }
    : {}
  )
}

module "temporal_cloud_workflow_plane" {
  source   = "../../../../modules/temporal_cloud_workflow_plane"
  for_each = local.temporal_cloud_resource_instances

  providers = {
    temporalcloud = temporalcloud.production[each.key]
  }

  namespace_name           = var.temporal_namespace_name
  namespace_region         = var.temporal_namespace_region
  namespace_retention_days = var.temporal_namespace_retention_days
}
