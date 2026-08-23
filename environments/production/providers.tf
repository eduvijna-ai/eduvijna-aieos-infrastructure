terraform {
  required_version = "= 1.12.5"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "= 2.99.1"
    }
    temporalcloud = {
      source  = "temporalio/temporalcloud"
      version = "= 1.7.0"
    }
  }
}

provider "digitalocean" {
  # Token MUST come from environment / deployment authority (DIGITALOCEAN_TOKEN).
  # Never commit tokens. CI for this repository must NOT hold production tokens.
}

provider "temporalcloud" {
  # api_key MUST come only from the provider-supported environment credential
  # channel (TEMPORAL_CLOUD_API_KEY) when a later Chief Architect gate authorizes
  # control-plane use. Never commit api_key. CI must NOT hold Temporal credentials.
  endpoint           = "saas-api.tmprl.cloud:443"
  allow_insecure     = false
  allowed_account_id = var.temporal_cloud_allowed_account_id
}
