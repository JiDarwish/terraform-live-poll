# Validation: a typo in -var-file fails at plan, before anything touches Azure.
variable "environment" {
  description = "Which environment this state file describes."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be \"dev\" or \"prod\"."
  }
}
