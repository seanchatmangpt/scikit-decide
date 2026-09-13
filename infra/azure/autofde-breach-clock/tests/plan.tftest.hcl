# Happy-path plan under a MOCKED azurerm provider.
#
# Harness shape (mock_provider + command = plan + assert{condition,
# error_message}) is adapted from
# /Users/sac/praxis/deploy/azure/ma-case-study/tests/container_group.tftest.hcl,
# the only *.tftest.hcl under ~. No credentials are needed, which is the
# whole point: there is no `az` on this machine.
#
# Directory is tests/ (not tests/unit/) to match `terraform test`'s default
# -test-directory, same as the praxis precedent.

mock_provider "azurerm" {}

variables {
  subscription_id          = "00000000-0000-0000-0000-000000000001"
  allowed_subscription_ids = ["00000000-0000-0000-0000-000000000001"]
  resource_group_name      = "skd-autofde-test-rg01"
  run_id                   = "run-0001"
  owner                    = "sac"
  expiry                   = "2026-12-31"
}

run "topology_and_guards" {
  command = plan

  assert {
    condition     = azurerm_resource_group.this.name == "skd-autofde-test-rg01"
    error_message = "resource group name must equal var.resource_group_name."
  }

  assert {
    condition     = startswith(azurerm_resource_group.this.name, "skd-autofde-test-")
    error_message = "resource group name must carry the sweepable prefix."
  }

  assert {
    condition     = azurerm_log_analytics_workspace.evidence.retention_in_days == 30
    error_message = "retention must be the bounded default of 30 days."
  }

  assert {
    condition     = azurerm_log_analytics_workspace.evidence.internet_ingestion_enabled == false
    error_message = "the evidence workspace must not be publicly ingestible."
  }

  assert {
    condition     = azurerm_log_analytics_workspace.evidence.internet_query_enabled == false
    error_message = "the evidence workspace must not be publicly queryable."
  }

  assert {
    condition     = azurerm_storage_account.evidence.public_network_access_enabled == false
    error_message = "the evidence sink must not be publicly exposed."
  }

  assert {
    condition     = azurerm_storage_account.evidence.allow_nested_items_to_be_public == false
    error_message = "the evidence sink must not permit anonymous blob access."
  }

  assert {
    condition     = azurerm_storage_container.evidence.container_access_type == "private"
    error_message = "the evidence container must be private."
  }

  assert {
    condition     = azurerm_logic_app_workflow.playbook.enabled == false
    error_message = "the response playbook must be provisioned disabled -- this repo computes plans, it does not actuate."
  }

  assert {
    condition     = azurerm_monitor_action_group.capture.enabled == false
    error_message = "the notification capture sink must be disabled; it captures, it does not page."
  }

  assert {
    condition     = azurerm_sentinel_alert_rule_scheduled.synthetic_breach.enabled == false
    error_message = "the synthetic detection must be provisioned disabled."
  }

  assert {
    condition     = azurerm_monitor_data_collection_endpoint.ingress.public_network_access_enabled == false
    error_message = "synthetic incident ingress must not be publicly reachable."
  }
}

run "mandatory_tags" {
  command = plan

  assert {
    condition     = azurerm_resource_group.this.tags["owner"] == "sac"
    error_message = "the mandatory owner tag must be present on every resource."
  }

  assert {
    condition     = azurerm_resource_group.this.tags["expiry"] == "2026-12-31"
    error_message = "the mandatory expiry tag must be present on every resource."
  }

  assert {
    condition     = azurerm_resource_group.this.tags["run"] == "run-0001"
    error_message = "the mandatory run tag must be present so orphan_sweep.sh can find leftovers."
  }

  assert {
    condition     = azurerm_resource_group.this.tags["environment"] == "test"
    error_message = "environment tag must be test."
  }

  assert {
    condition     = azurerm_resource_group.this.tags["managed-by"] == "terraform"
    error_message = "layer-1 managed-by tag must survive the three-layer merge."
  }

  assert {
    condition     = azurerm_resource_group.this.tags["workload"] == "autofde-breach-clock"
    error_message = "layer-1 workload tag must survive the three-layer merge."
  }

  assert {
    condition     = azurerm_log_analytics_workspace.evidence.tags["run"] == "run-0001"
    error_message = "the run tag must reach the evidence workspace, not only the resource group."
  }

  assert {
    condition     = azurerm_storage_account.evidence.tags["expiry"] == "2026-12-31"
    error_message = "the expiry tag must reach the evidence sink."
  }
}

run "no_perpetual_diff_tag" {
  command = plan

  # /Users/sac/yawl/terraform tags CreatedAt = timestamp(), which forces a
  # diff on every plan. This asserts it was not copied.
  assert {
    condition     = !can(azurerm_resource_group.this.tags["CreatedAt"])
    error_message = "no timestamp()-derived tag may be applied; it forces a perpetual diff."
  }
}
