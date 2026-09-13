# Ephemeral Azure incident-response demo environment ("autofde breach clock").
#
# Authored refusal-first. Every safety invariant is enforced at PLAN time --
# either by a `validation` block in variables.tf or by a `precondition` in
# this file -- so `terraform plan` (and therefore `terraform test` with a
# mocked provider) refuses before any credential is ever needed.
#
# LOCAL PRECEDENT LEDGER, so confidence is not transferred across resources
# it was never earned for. Across all 702 .tf files under ~:
#   azurerm_log_analytics_workspace ......... 14 uses -> precedent exists
#   managed identity as a dynamic "identity" . uses    -> precedent exists
#   azurerm_role_assignment .................. 3 uses  -> precedent exists
#   azurerm_sentinel_*  ...................... 0 uses  -> NO LOCAL PRECEDENT
#   azurerm_logic_app_* ...................... 0 uses  -> NO LOCAL PRECEDENT
# The Sentinel and Logic App resources below are greenfield in this
# codebase. Their argument shapes are asserted only by `terraform validate`
# against the azurerm ~> 3.90 schema and by mocked plans; nothing here has
# ever been applied against Azure, and no local deployment exists to compare
# against. Read those two blocks with that in mind.

# ---------------------------------------------------------------------------
# Guardrails. This resource creates nothing; it exists so the invariants that
# cannot live in a single variable's `validation` block (cross-variable and
# post-merge conditions) still fail at PLAN time. terraform_data is a
# built-in managed resource, so it needs no provider and works under
# mock_provider.
# ---------------------------------------------------------------------------
resource "terraform_data" "guardrails" {
  input = {
    run_id      = var.run_id
    environment = var.environment
  }

  lifecycle {
    precondition {
      condition     = local.subscription_allowed
      error_message = "REFUSED: subscription_id ${var.subscription_id} is not in allowed_subscription_ids. The allowlist defaults to [] -- an approved test subscription must be named explicitly. The active `az` CLI context is never consulted."
    }

    precondition {
      condition     = local.mandatory_tags_present
      error_message = "REFUSED: the mandatory owner/expiry/run tags did not survive the tag merge. var.tags must not override them."
    }

    precondition {
      condition     = local.managed_identity_in_use
      error_message = "REFUSED: a user-assigned managed identity must be used; no credential-bearing alternative is offered."
    }

    precondition {
      condition     = !var.enable_production_actuation && !var.enable_real_notification && !var.enable_destructive_identity_action
      error_message = "REFUSED: production actuation, real notification, and destructive identity actions are all permanently disabled in this environment."
    }
  }
}

# ---------------------------------------------------------------------------
# Isolated blast radius: one resource group, named so an orphan sweep can
# find it by prefix + run tag alone.
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------------------
# Evidence + telemetry store. Retention is bounded by var.log_retention_days
# (7-30). Both internet ingestion and internet query are disabled: an
# evidence store for an incident-response demo must not be publicly exposed.
# PRECEDENT: 14 local uses of this resource type.
# ---------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "evidence" {
  name                       = "${local.name_prefix}-law"
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  sku                        = "PerGB2018"
  retention_in_days          = var.log_retention_days
  internet_ingestion_enabled = false
  internet_query_enabled     = false
  tags                       = local.tags

  lifecycle {
    precondition {
      condition     = var.log_retention_days <= 30
      error_message = "REFUSED: unbounded/long retention is not permitted in an ephemeral environment."
    }
  }
}

# ---------------------------------------------------------------------------
# Sentinel onboarding + one synthetic detection.
# NO LOCAL PRECEDENT -- zero azurerm_sentinel_* resources exist anywhere
# under ~. Argument names below are from the azurerm ~> 3.90 schema only.
#
# The detection is deliberately SYNTHETIC: it queries a Heartbeat row that
# the demo harness writes, not any real security signal, and it is created
# disabled.
# ---------------------------------------------------------------------------
resource "azurerm_sentinel_log_analytics_workspace_onboarding" "this" {
  workspace_id = azurerm_log_analytics_workspace.evidence.id
}

resource "azurerm_sentinel_alert_rule_scheduled" "synthetic_breach" {
  name                       = "${local.name_prefix}-synthetic-breach"
  log_analytics_workspace_id = azurerm_sentinel_log_analytics_workspace_onboarding.this.workspace_id
  display_name               = "Synthetic breach clock trigger (${var.run_id})"
  severity                   = "Low"
  enabled                    = false
  query_frequency            = "PT1H"
  query_period               = "PT1H"

  query = <<-KQL
    Heartbeat
    | where Computer startswith "autofde-synthetic-"
    | project TimeGenerated, Computer
  KQL

  lifecycle {
    precondition {
      condition     = !var.enable_production_actuation
      error_message = "REFUSED: the detection rule may not be armed for production actuation."
    }
  }
}

# ---------------------------------------------------------------------------
# Synthetic incident ingress. A data collection endpoint with public network
# access disabled -- the demo harness pushes synthetic incident rows here;
# nothing on the public internet can.
# ---------------------------------------------------------------------------
resource "azurerm_monitor_data_collection_endpoint" "ingress" {
  name                          = "${local.name_prefix}-dce"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  public_network_access_enabled = false
  description                   = "Synthetic incident ingress for the autofde breach-clock demo. Accepts test fixtures only."
  tags                          = local.tags
}

# ---------------------------------------------------------------------------
# Responder identity. User-assigned managed identity, always. This is the
# only authentication mechanism this configuration offers -- there is no
# service-principal secret variable to set.
# PRECEDENT: managed identity as a dynamic "identity" toggle exists locally;
# here it is unconditional rather than toggled, because "identity optional"
# is itself the hazard.
# ---------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "responder" {
  name                = "${local.name_prefix}-uami"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = local.tags
}

# Least privilege: "Reader", scoped to this configuration's own resource
# group and nothing wider. Contributor/Owner are not reachable from any
# variable -- the role name is a literal, not an input.
# PRECEDENT: 3 local uses of azurerm_role_assignment.
resource "azurerm_role_assignment" "responder_reader" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.responder.principal_id

  lifecycle {
    precondition {
      condition     = !var.enable_destructive_identity_action
      error_message = "REFUSED: destructive identity actions are not permitted; the responder identity is Reader-scoped to its own resource group."
    }
  }
}

# ---------------------------------------------------------------------------
# Response playbook.
# NO LOCAL PRECEDENT -- zero azurerm_logic_app_* resources exist anywhere
# under ~. Argument names below are from the azurerm ~> 3.90 schema only.
#
# Created DISABLED and with no trigger or action wired. It exists so the
# demo can show a playbook being selected; it cannot run.
# ---------------------------------------------------------------------------
resource "azurerm_logic_app_workflow" "playbook" {
  name                = "${local.name_prefix}-playbook"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  enabled             = false
  tags                = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.responder.id]
  }

  lifecycle {
    precondition {
      condition     = !var.enable_production_actuation
      error_message = "REFUSED: the response playbook may not be enabled for production actuation. This repository computes candidate plans; it does not actuate."
    }
  }
}

# ---------------------------------------------------------------------------
# Notification capture SINK. Deliberately has no email/SMS/voice/webhook
# receiver of any kind: the action group is a capture point whose notified
# set is empty. enable_real_notification is validated to false, so there is
# no code path that adds a recipient -- the guard is enforced twice, once in
# variables.tf and once here, because a notification reaching a real human
# from a demo is the highest-cost mistake available in this file.
# ---------------------------------------------------------------------------
resource "azurerm_monitor_action_group" "capture" {
  name                = "${local.name_prefix}-capture"
  resource_group_name = azurerm_resource_group.this.name
  short_name          = substr(var.run_id, 0, 12)
  enabled             = false
  tags                = local.tags

  lifecycle {
    precondition {
      condition     = !var.enable_real_notification
      error_message = "REFUSED: real notification recipients may not be provisioned. This action group captures; it does not page."
    }
  }
}

# ---------------------------------------------------------------------------
# Evidence sink. Private, TLS 1.2 minimum, no public network access, no
# anonymous blob access. An evidence store that is publicly reachable is
# worse than no evidence store.
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "evidence" {
  name                            = local.evidence_storage_name
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  public_network_access_enabled   = false
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  tags                            = local.tags

  lifecycle {
    precondition {
      condition     = local.mandatory_tags_present
      error_message = "REFUSED: the evidence sink must carry owner/expiry/run tags so it can be swept."
    }
  }
}

resource "azurerm_storage_container" "evidence" {
  name                  = "incident-evidence"
  storage_account_name  = azurerm_storage_account.evidence.name
  container_access_type = "private"
}
