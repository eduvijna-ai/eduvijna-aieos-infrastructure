# WPI-I01 — Temporal Cloud workflow-plane source model only.
# Manages Namespace + two service accounts. Does NOT manage API keys.
# Does NOT authorize Temporal Cloud mutation / apply / commercial enrollment.

resource "temporalcloud_namespace" "production" {
  name           = var.namespace_name
  regions        = [var.namespace_region] # structurally exactly one region — HA not authorized
  retention_days = var.namespace_retention_days
  api_key_auth   = true

  namespace_lifecycle = {
    enable_delete_protection = true
  }
}

resource "temporalcloud_service_account" "workflow_dispatcher" {
  name           = "${var.namespace_name}-workflow-dispatcher"
  account_access = "read"

  namespace_accesses = [
    {
      namespace_id = temporalcloud_namespace.production.id
      permission   = "write"
    }
  ]
}

resource "temporalcloud_service_account" "temporal_worker" {
  name           = "${var.namespace_name}-temporal-worker"
  account_access = "read"

  namespace_accesses = [
    {
      namespace_id = temporalcloud_namespace.production.id
      permission   = "write"
    }
  ]
}
