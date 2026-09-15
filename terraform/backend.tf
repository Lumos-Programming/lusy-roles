terraform {
  backend "gcs" {
    bucket = "lusy-roles-state"
    prefix = "lusy-roles/production"
  }
}
