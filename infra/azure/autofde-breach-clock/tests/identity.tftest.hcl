# Identity and least-privilege assertions, mocked provider, plan only.

# The resource group id is normally unknown at plan time, so an assertion
# comparing the role assignment's scope against it fails with "Unknown
# condition value" -- observed, not anticipated, on the first run of this
# file. Giving the mocked resource group a deterministic id makes the scope
# invariant checkable under `command = plan`, which is the only command this
# suite is permitted to use.
mock_provider "azurerm" {}

# `mock_resource ... defaults` was tried first and did NOT make the id known
# during plan; Terraform's own error text names the working mechanism, and
# `override_during = plan` is what actually works. Recorded because the
# non-working form looks equally plausible.
override_resource {
  target          = azurerm_resource_group.this
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/skd-autofde-test-rg01"
  }
}

variables {
  subscription_id          = "00000000-0000-0000-0000-000000000001"
  allowed_subscription_ids = ["00000000-0000-0000-0000-000000000001"]
  resource_group_name      = "skd-autofde-test-rg01"
  run_id                   = "run-0001"
  owner                    = "sac"
  expiry                   = "2026-12-31"
}

run "managed_identity_is_used" {
  command = plan

  assert {
    condition     = azurerm_user_assigned_identity.responder.name == "skd-autofde-run-0001-uami"
    error_message = "a user-assigned managed identity must be created."
  }

  assert {
    condition     = length(azurerm_logic_app_workflow.playbook.identity) == 1
    error_message = "the response playbook must carry exactly one identity block."
  }

  assert {
    condition     = azurerm_logic_app_workflow.playbook.identity[0].type == "UserAssigned"
    error_message = "the playbook must authenticate via a user-assigned managed identity, never a secret."
  }

  assert {
    condition     = length(azurerm_logic_app_workflow.playbook.identity[0].identity_ids) == 1
    error_message = "the playbook must bind exactly the responder identity."
  }
}

run "role_assignment_is_least_privilege" {
  command = plan

  assert {
    condition     = azurerm_role_assignment.responder_reader.role_definition_name == "Reader"
    error_message = "the responder identity must hold Reader and nothing wider. The role name is a literal, not a variable."
  }

  assert {
    condition     = azurerm_role_assignment.responder_reader.scope == azurerm_resource_group.this.id
    error_message = "the role assignment must be scoped to this configuration's own resource group, never to the subscription."
  }
}

run "no_credential_material_is_output" {
  command = plan

  # shared_access_key_enabled = false means there is no storage key to leak
  # even if an output were added carelessly later.
  assert {
    condition     = azurerm_storage_account.evidence.shared_access_key_enabled == false
    error_message = "the evidence sink must not issue shared access keys; the managed identity is the only credential."
  }
}
