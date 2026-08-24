resource "digitalocean_app" "this" {
  project_id = var.project_id

  spec {
    name   = var.app_name
    region = var.region

    vpc {
      id = var.vpc_id
    }

    worker {
      name               = var.app_name
      run_command        = var.run_command
      instance_count     = var.instance_count
      instance_size_slug = var.instance_size_slug

      image {
        registry_type = var.image_registry_type
        repository    = var.image_repository
        digest        = var.image_digest

        deploy_on_push {
          enabled = false
        }
      }
    }
  }
}
