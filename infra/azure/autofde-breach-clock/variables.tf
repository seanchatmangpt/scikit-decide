# Input variables.
#
# Every variable carries `nullable = false` (praxis precedent:
# /Users/sac/praxis/deploy/azure/ma-case-study/variables.tf). Every safety
# variable additionally carries a `validation` block, an idiom this repo's
# nearest local precedent for is /Users/sac/yawl/terraform/variables.tf
# (`contains([...], var.environment)` and
# `can(regex("^[a-z][a-z0-9-]{1,28}[a-z0-9]$", var.project_name))`) -- the
# praxis precedent has zero validation blocks, so the shape below is yawl's,
# not praxis's.
#
# DEFAULTS ARE REFUSALS. `allowed_subscription_ids` defaults to `[]`, so a
# fresh `terraform plan` with no operator input refuses rather than
# proceeding. This is the single most important line in the file.

variable "project_name" {
  type        = string
  default     = "skd-autofde"
  description = "Project slug used for resource naming. Shape adapted from /Users/sac/yawl/terraform/variables.tf."
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,28}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-30 characters, lowercase alphanumeric with hyphens, starting with a letter."
  }
}

variable "environment" {
  type        = string
  default     = "test"
  description = "Deployment environment. This configuration is an EPHEMERAL incident-response demo environment and refuses any value but \"test\"."
  nullable    = false

  validation {
    # NOTE the deliberate narrowing versus yawl's
    # contains(["dev","staging","prod"], ...): this configuration accepts
    # exactly one value. "dev" and "staging" are rejected too -- an
    # incident-response demo that provisions notification sinks and an
    # identity has no business existing outside a disposable test env.
    condition     = var.environment == "test"
    error_message = "environment must be exactly \"test\". This configuration refuses to plan for dev, staging, or prod."
  }
}

variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region for the ephemeral incident-response environment."
  nullable    = false
}

variable "allowed_subscription_ids" {
  type        = list(string)
  default     = []
  description = <<-EOT
    Explicit allowlist of subscription IDs this configuration may target.
    DEFAULTS TO EMPTY, which means the default state of this configuration is
    refusal: with no allowlist entry, the subscription guard precondition in
    main.tf fails at plan time. The operator must name an approved test
    subscription deliberately.
  EOT
  nullable    = false
}

variable "subscription_id" {
  type        = string
  description = <<-EOT
    Subscription ID to target, supplied EXPLICITLY by the operator. Never
    inferred from an active `az` CLI context -- see providers.tf. No default:
    there is no safe default subscription, and a default would let a plan
    succeed without an operator ever having named a target.
  EOT
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Name of the isolated resource group. Must be prefixed \"skd-autofde-test-\" so an orphan sweep can identify this configuration's blast radius by name alone."
  nullable    = false

  validation {
    condition     = startswith(var.resource_group_name, "skd-autofde-test-")
    error_message = "resource_group_name must start with \"skd-autofde-test-\"."
  }

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,88}[a-z0-9]$", var.resource_group_name))
    error_message = "resource_group_name must be lowercase alphanumeric with hyphens, starting with a letter (Azure RG name rules, narrowed)."
  }
}

variable "run_id" {
  type        = string
  description = <<-EOT
    Identifier for one ephemeral run of this environment. Tagged onto every
    resource so scripts/orphan_sweep.sh can find leftovers.

    NEW CONVENTION, explicitly labelled as such: there is no existing `run_id`
    convention in any IaC under ~. The nearest existing idiom is
    `random_string.suffix`, which is deliberately NOT used here -- a random
    suffix is unknown to the operator before apply, whereas an orphan sweep
    needs a value the caller already holds.
  EOT
  nullable    = false

  validation {
    condition     = length(trimspace(var.run_id)) > 0
    error_message = "run_id must be non-empty."
  }

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$", var.run_id))
    error_message = "run_id must be lowercase alphanumeric with hyphens, 2-40 chars."
  }
}

variable "owner" {
  type        = string
  description = "Accountable human for this ephemeral environment. Emitted as the mandatory `owner` tag."
  nullable    = false

  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner must be non-empty; the mandatory owner tag cannot be blank."
  }
}

variable "expiry" {
  type        = string
  description = "RFC3339 date (YYYY-MM-DD) after which this environment is an orphan and may be swept. Emitted as the mandatory `expiry` tag. NOT `timestamp()`: /Users/sac/yawl/terraform's CreatedAt = timestamp() tag forces a perpetual diff on every plan, so it is deliberately not copied."
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", var.expiry))
    error_message = "expiry must be a YYYY-MM-DD date."
  }
}

variable "enable_real_notification" {
  type        = bool
  default     = false
  description = "MUST remain false. When false, the notification capture sink is provisioned with zero real recipients -- no email, no SMS, no voice. True would page a real human from a demo."
  nullable    = false

  validation {
    condition     = var.enable_real_notification == false
    error_message = "enable_real_notification must be false. This configuration refuses to provision real notification recipients."
  }
}

variable "enable_production_actuation" {
  type        = bool
  default     = false
  description = "MUST remain false. The response playbook is provisioned disabled and unwired; true would let a demo playbook act."
  nullable    = false

  validation {
    condition     = var.enable_production_actuation == false
    error_message = "enable_production_actuation must be false. This configuration computes a response, it does not actuate one."
  }
}

variable "enable_destructive_identity_action" {
  type        = bool
  default     = false
  description = "MUST remain false. Guards the role assignment against escalation beyond the least-privilege reader role."
  nullable    = false

  validation {
    condition     = var.enable_destructive_identity_action == false
    error_message = "enable_destructive_identity_action must be false. This configuration refuses destructive identity permissions."
  }
}

variable "log_retention_days" {
  type        = number
  default     = 30
  description = "Log Analytics retention. Bounded 7-30: unbounded retention on an ephemeral demo environment is an evidence-hoarding hazard, not a feature."
  nullable    = false

  validation {
    condition     = var.log_retention_days >= 7 && var.log_retention_days <= 30
    error_message = "log_retention_days must be between 7 and 30 (retention is deliberately bounded for an ephemeral environment)."
  }
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "(Optional) Additional tags merged onto every resource. Third and lowest-precedence layer of the tag merge in locals.tf."
  nullable    = false
}
