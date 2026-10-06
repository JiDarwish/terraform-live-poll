# variable "environment" lives in main.tf, because main.tf is the slide.

variable "vote_storage_account_name" {
  description = "Globally unique name of the vote storage account. Fixed per environment, no random suffix."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.vote_storage_account_name))
    error_message = "vote_storage_account_name must be 3-24 lowercase letters and digits."
  }
}
