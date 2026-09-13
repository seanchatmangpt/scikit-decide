# Provider configuration.
#
# REFUSAL-FIRST INVARIANT: `subscription_id` is bound from an explicit
# operator-supplied variable, never inferred from an ambient `az` CLI
# context. The azurerm provider will otherwise fall back to the active
# `az account show` subscription, which is exactly the failure mode this
# configuration exists to make impossible -- an operator with a production
# context selected would silently plan against production.
#
# There is no `az` on this machine (`which az` returns nothing, verified),
# but this configuration must not depend on that being true. Setting
# subscription_id explicitly makes the refusal structural rather than
# environmental.
#
# All validated invariants are enforced at PLAN time (variable `validation`
# blocks + resource `precondition`s), not here -- provider blocks cannot
# carry conditions.

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id

  # No client_id/client_secret/tenant_id: this configuration is authored to
  # be planned with a mocked provider only. Supplying credential arguments
  # here would create a path where a real apply becomes one `terraform apply`
  # away.
}
