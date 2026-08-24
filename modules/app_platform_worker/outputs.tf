output "app_id" {
  value = digitalocean_app.this.id
}

output "app_urn" {
  value = digitalocean_app.this.urn
}

output "active_deployment_id" {
  value = digitalocean_app.this.active_deployment_id
}
