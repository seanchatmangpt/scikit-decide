# Outputs.
#
# No secret, connection string, or access key is emitted. The evidence
# storage account sets shared_access_key_enabled = false, so there is no key
# to leak here even by accident.

output "resource_group_name" {
  description = "Name of the isolated resource group holding this ephemeral environment."
  value       = azurerm_resource_group.this.name
}

output "run_id" {
  description = "Run identifier tagged onto every resource. Feed this to scripts/orphan_sweep.sh."
  value       = var.run_id
}

output "expiry" {
  description = "Date after which this environment is an orphan and may be swept."
  value       = var.expiry
}

output "tags" {
  description = "The merged tag set applied to every resource, including the mandatory owner/expiry/run tags."
  value       = local.tags
}

output "responder_identity_id" {
  description = "Resource ID of the user-assigned managed identity used by the response playbook."
  value       = azurerm_user_assigned_identity.responder.id
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the evidence Log Analytics workspace."
  value       = azurerm_log_analytics_workspace.evidence.id
}

output "playbook_enabled" {
  description = "Always false. Emitted so a caller can assert the playbook is inert without reading the config."
  value       = azurerm_logic_app_workflow.playbook.enabled
}

output "notification_capture_enabled" {
  description = "Always false. The notification sink captures; it does not page."
  value       = azurerm_monitor_action_group.capture.enabled
}

output "refusal_posture" {
  description = "Machine-readable summary of the safety switches, all of which are validated false at plan time."
  value = {
    environment                        = var.environment
    subscription_allowlisted           = local.subscription_allowed
    enable_real_notification           = var.enable_real_notification
    enable_production_actuation        = var.enable_production_actuation
    enable_destructive_identity_action = var.enable_destructive_identity_action
    managed_identity_in_use            = local.managed_identity_in_use
  }
}
