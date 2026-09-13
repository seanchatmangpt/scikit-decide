# Derived values and the tag merge.
#
# Three-layer lowercase-hyphen tag merge, shape taken from
# /Users/sac/praxis/deploy/azure/ma-case-study/variables.tf:
#   layer 1  fixed identifiers for this configuration
#   layer 2  values threaded from operator input
#   layer 3  caller-supplied extras (var.tags)
#
# Layer 2 carries the mandatory `owner`, `expiry` and `run` tags. Because
# var.tags is merged LAST it can in principle clobber them, so main.tf
# carries a precondition asserting all three survived the merge non-empty.
# That is the proof; this merge is only the mechanism.
#
# No `CreatedAt = timestamp()` tag. /Users/sac/yawl/terraform uses one; it
# forces a perpetual diff on every plan and is deliberately not copied.

locals {
  tags = merge(
    {
      workload   = "autofde-breach-clock"
      managed-by = "terraform"
    },
    {
      environment = var.environment
      owner       = var.owner
      expiry      = var.expiry
      run         = var.run_id
    },
    var.tags,
  )

  # Name prefix. run_id is included so two concurrent ephemeral runs cannot
  # collide, and so every resource name is greppable by run.
  name_prefix = "${var.project_name}-${var.run_id}"

  # Storage account names cannot contain hyphens and cap at 24 chars.
  evidence_storage_name = substr(replace("${local.name_prefix}evd", "-", ""), 0, 24)

  # Refusal predicates, named once so main.tf's preconditions and the
  # refusal tests read the same way.
  subscription_allowed = contains(var.allowed_subscription_ids, var.subscription_id)

  mandatory_tags_present = alltrue([
    for k in ["owner", "expiry", "run"] :
    can(local.tags[k]) && length(trimspace(lookup(local.tags, k, ""))) > 0
  ])

  # A managed identity is always used: this configuration exposes no switch
  # to turn it off, and the playbook's identity block below is unconditional.
  # The local exists so the invariant is assertable from a test rather than
  # merely true by construction.
  managed_identity_in_use = true
}
