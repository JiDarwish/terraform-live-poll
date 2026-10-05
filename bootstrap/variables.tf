variable "subscription_id" {
  description = "Azure subscription that holds every livepoll resource group."
  type        = string
}

variable "location" {
  description = "Azure region for the bootstrap resource groups and the state account."
  type        = string
  default     = "westeurope"
}

variable "presenter_object_id" {
  description = "Entra object id of the presenter, who runs bootstrap and presents the demo."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.presenter_object_id))
    error_message = "presenter_object_id must be an Entra object id (a GUID), not a UPN or e-mail address."
  }
}
