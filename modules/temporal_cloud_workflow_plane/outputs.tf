output "namespace_id" {
  description = "Non-secret Temporal Cloud Namespace ID."
  value       = temporalcloud_namespace.production.id
}

output "namespace_grpc_address" {
  description = "Non-secret Namespace gRPC address for API-key client connections (Namespace Endpoint)."
  value       = temporalcloud_namespace.production.endpoints.grpc_address
}

output "workflow_dispatcher_service_account_id" {
  description = "Non-secret WORKFLOW_DISPATCHER Temporal Cloud service-account ID."
  value       = temporalcloud_service_account.workflow_dispatcher.id
}

output "temporal_worker_service_account_id" {
  description = "Non-secret TEMPORAL_WORKER Temporal Cloud service-account ID."
  value       = temporalcloud_service_account.temporal_worker.id
}
