variable "subscription_id" {
  description = "Azure subscription that holds every livepoll resource group."
  type        = string
}

variable "location" {
  description = "Azure region for the bootstrap resource groups and the state account."
  type        = string
  default     = "westeurope"
}

variable "presenter_object_ids" {
  description = "Entra object ids of the presenters, keyed by first name, e.g. { ji = \"...\", fokke = \"...\" }."
  type        = map(string)

  validation {
    condition = alltrue([
      for id in values(var.presenter_object_ids) :
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))
    ])
    error_message = "Each presenter_object_ids value must be an Entra object id (a GUID), not a UPN or e-mail address."
  }
}
