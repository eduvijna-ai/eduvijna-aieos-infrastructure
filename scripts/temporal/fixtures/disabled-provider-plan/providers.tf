terraform {
  required_version = "= 1.12.5"

  required_providers {
    temporalcloud = {
      source  = "temporalio/temporalcloud"
      version = "= 1.7.0"
    }
  }
}

provider "temporalcloud" {
  alias    = "production"
  for_each = local.temporal_cloud_provider_instances

  endpoint           = "saas-api.tmprl.cloud:443"
  allow_insecure     = false
  allowed_account_id = each.value
}
