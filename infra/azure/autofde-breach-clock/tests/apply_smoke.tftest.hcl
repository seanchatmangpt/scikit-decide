# AUTHORED, NEVER RUN.
#
# This file contains ZERO live `run` blocks, deliberately. `terraform test`
# globs tests/*.tftest.hcl with no skip mechanism, so the only way an
# apply-tier file can sit in this directory without being executed by a bare
# `terraform test` is for its run blocks to be commented out. Uncommenting
# them is the deliberate, reviewable act that arms this file. A `run` block
# guarded by a false assertion was tried first and rejected: it would make
# the default suite red, which trains an operator to ignore red.
#
# Standing: NOT_RUN, with TWO named blockers, both of which must clear
# independently:
#
#   BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION
#     No approved disposable Azure subscription exists for this work, and
#     var.allowed_subscription_ids defaults to [] precisely so that this is
#     a refusal rather than an oversight.
#
#   BLOCKED:AZURE_CLI_ABSENT
#     `which az` returns nothing on this machine (verified). Even holding an
#     approved subscription id there is no path to authenticate.
#
# Clearing one blocker does not make this file runnable.
#
# NOTE the absence of a `mock_provider "azurerm" {}` block. That absence is
# load-bearing: `command = apply` under a mocked provider is a no-op that
# LOOKS like apply-tier evidence and is not. The apply tier means real
# resources in a real subscription, created and then destroyed by
# `terraform test`. If this file is ever armed, it must be armed unmocked.
#
# ---------------------------------------------------------------------------
# PRECONDITIONS FOR ARMING, ALL REQUIRED:
#   1. An approved disposable Azure test subscription exists; its id is
#      recorded in an operator-supplied allowlist (not committed here).
#   2. Azure CLI is installed and authenticated to that subscription ONLY.
#   3. A named human has accepted the cost and blast radius, recorded as
#      var.owner, with var.expiry set to a near date.
#   4. scripts/orphan_sweep.sh has been dry-run against the intended run_id
#      so the teardown path is known to work BEFORE anything is created.
# ---------------------------------------------------------------------------

# variables {
#   subscription_id          = "<approved test subscription guid>"
#   allowed_subscription_ids = ["<approved test subscription guid>"]
#   resource_group_name      = "skd-autofde-test-rg01"
#   run_id                   = "run-0001"
#   owner                    = "<accountable human>"
#   expiry                   = "<YYYY-MM-DD, near>"
# }
#
# run "real_apply_creates_isolated_environment" {
#   command = apply
#
#   assert {
#     condition     = azurerm_resource_group.this.location == var.location
#     error_message = "resource group must land in the requested region."
#   }
#
#   assert {
#     condition     = azurerm_user_assigned_identity.responder.principal_id != ""
#     error_message = "the managed identity must receive a real principal id."
#   }
#
#   assert {
#     condition     = azurerm_logic_app_workflow.playbook.enabled == false
#     error_message = "the playbook must be inert even after a real apply."
#   }
#
#   assert {
#     condition     = azurerm_role_assignment.responder_reader.role_definition_name == "Reader"
#     error_message = "the responder identity must hold Reader after a real apply."
#   }
# }
#
# run "real_apply_evidence_sink_is_private" {
#   command = apply
#
#   assert {
#     condition     = azurerm_storage_account.evidence.public_network_access_enabled == false
#     error_message = "the evidence sink must be unreachable from the public internet after a real apply."
#   }
#
#   assert {
#     condition     = azurerm_storage_container.evidence.container_access_type == "private"
#     error_message = "the evidence container must be private after a real apply."
#   }
# }
