# THE FILE THAT CARRIES THE EVIDENCE.
#
# Every safety invariant in variables.tf / main.tf is a guard. A guard that
# was written but never proved to reject anything is worth nothing. Each
# `run` block below feeds a deliberately bad input and asserts, via
# `expect_failures`, that Terraform REFUSES at plan time.
#
# `expect_failures` targets:
#   var.<name>              -> a `validation` block in variables.tf rejected it
#   terraform_data.guardrails -> a `precondition` in main.tf rejected it
#
# All runs are `command = plan`. Nothing here can reach Azure: the provider
# is mocked and the plan never completes for these inputs anyway.

mock_provider "azurerm" {}

# Known-good baseline; each run below perturbs exactly one field.
variables {
  subscription_id          = "00000000-0000-0000-0000-000000000001"
  allowed_subscription_ids = ["00000000-0000-0000-0000-000000000001"]
  resource_group_name      = "skd-autofde-test-rg01"
  run_id                   = "run-0001"
  owner                    = "sac"
  expiry                   = "2026-12-31"
}

# --- environment must be exactly "test" ------------------------------------

run "refuses_environment_prod" {
  command = plan

  variables {
    environment = "prod"
  }

  expect_failures = [var.environment]
}

run "refuses_environment_dev" {
  command = plan

  variables {
    environment = "dev"
  }

  # Narrower than the yawl precedent on purpose: "dev" is a legal value
  # there and an illegal one here.
  expect_failures = [var.environment]
}

# --- subscription must be explicitly allowlisted ---------------------------

run "refuses_subscription_not_in_allowlist" {
  command = plan

  variables {
    subscription_id          = "00000000-0000-0000-0000-0000000000ff"
    allowed_subscription_ids = ["00000000-0000-0000-0000-000000000001"]
  }

  expect_failures = [terraform_data.guardrails]
}

run "refuses_empty_allowlist" {
  command = plan

  variables {
    # This is the DEFAULT value of allowed_subscription_ids. Restated
    # explicitly here so the test proves the default state is refusal rather
    # than relying on the reader to check variables.tf.
    allowed_subscription_ids = []
  }

  expect_failures = [terraform_data.guardrails]
}

run "refuses_non_guid_subscription" {
  command = plan

  variables {
    subscription_id = "my-azure-sub"
  }

  expect_failures = [var.subscription_id]
}

# --- resource group name must carry the sweepable prefix -------------------

run "refuses_unprefixed_resource_group" {
  command = plan

  variables {
    resource_group_name = "prod-incident-response"
  }

  expect_failures = [var.resource_group_name]
}

run "refuses_near_miss_prefix" {
  command = plan

  variables {
    # "skd-autofde-" without "test-" -- the near miss is the dangerous case.
    resource_group_name = "skd-autofde-rg01"
  }

  expect_failures = [var.resource_group_name]
}

# --- the three actuation switches ------------------------------------------

run "refuses_real_notification" {
  command = plan

  variables {
    enable_real_notification = true
  }

  expect_failures = [var.enable_real_notification]
}

run "refuses_production_actuation" {
  command = plan

  variables {
    enable_production_actuation = true
  }

  expect_failures = [var.enable_production_actuation]
}

run "refuses_destructive_identity_action" {
  command = plan

  variables {
    enable_destructive_identity_action = true
  }

  expect_failures = [var.enable_destructive_identity_action]
}

# --- run_id must be non-empty ----------------------------------------------

run "refuses_empty_run_id" {
  command = plan

  variables {
    run_id = ""
  }

  expect_failures = [var.run_id]
}

run "refuses_whitespace_run_id" {
  command = plan

  variables {
    run_id = "   "
  }

  expect_failures = [var.run_id]
}

# --- mandatory owner / expiry tags -----------------------------------------

run "refuses_empty_owner" {
  command = plan

  variables {
    owner = ""
  }

  expect_failures = [var.owner]
}

run "refuses_malformed_expiry" {
  command = plan

  variables {
    expiry = "next tuesday"
  }

  expect_failures = [var.expiry]
}

run "refuses_tag_override_that_blanks_owner" {
  command = plan

  variables {
    # var.tags is the LAST layer of the three-layer merge, so it can clobber
    # the mandatory tags. The guardrails precondition catches that; this run
    # is the proof that it does.
    tags = {
      owner = ""
    }
  }

  # Two guards fire, not one: the central guardrails precondition AND the
  # evidence sink's own. Both must be listed or terraform test reports the
  # unlisted one as an unexpected failure -- observed on the first run of
  # this file. Listing both is also the more honest record: the tag
  # invariant is enforced in two places on purpose.
  expect_failures = [
    terraform_data.guardrails,
    azurerm_storage_account.evidence,
  ]
}

run "refuses_tag_override_that_blanks_run" {
  command = plan

  variables {
    tags = {
      run = ""
    }
  }

  expect_failures = [
    terraform_data.guardrails,
    azurerm_storage_account.evidence,
  ]
}

# --- bounded retention -----------------------------------------------------

run "refuses_unbounded_retention" {
  command = plan

  variables {
    log_retention_days = 3650
  }

  expect_failures = [var.log_retention_days]
}

# --- project naming --------------------------------------------------------

run "refuses_malformed_project_name" {
  command = plan

  variables {
    project_name = "Prod_AutoFDE"
  }

  expect_failures = [var.project_name]
}

# --- managed identity ------------------------------------------------------
#
# There is NO run block feeding "managed identity disabled", because no such
# input exists: the configuration offers no switch to turn the managed
# identity off, and no secret-bearing alternative. Stated plainly rather than
# faked with a vacuous expect_failures -- the invariant here is proved by
# absence of an input plus the positive assertions in identity.tftest.hcl,
# not by a refusal test.
