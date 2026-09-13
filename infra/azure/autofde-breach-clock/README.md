# autofde-breach-clock — ephemeral Azure incident-response demo environment

An **ephemeral** Azure environment for an incident-response demo, authored
refusal-first and validated with **mocked providers only**. It has never been
applied. It is not intended to be applied from this repository.

This configuration follows the same law as the rest of the repo: *it computes
a candidate environment; it does not actuate one.* The response playbook is
provisioned disabled, the notification sink has zero recipients, and the
detection rule is a synthetic query over a Heartbeat table.

## Standing

| Boundary | Standing | Evidence |
|---|---|---|
| `terraform fmt -check -recursive` | `ALIVE` | exit 0 |
| `terraform init -backend=false` | `ALIVE` | azurerm v3.117.1 installed |
| `terraform validate` | `ALIVE` | "The configuration is valid." |
| `terraform test` (mocked, plan-only) | `ALIVE` | 24 passed, 0 failed |
| refusal guards proved to refuse | `ALIVE` | 18 `expect_failures` runs pass |
| `terraform apply` against real Azure | `NOT_RUN` | `BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION` **and** `BLOCKED:AZURE_CLI_ABSENT` |
| `scripts/orphan_sweep.sh` delete path | `NOT_RUN` | nothing has ever been created to sweep |

The apply row carries **two independent blockers**. Clearing one does not
make it runnable.

## Refusal-first design

Terraform refuses at **plan** time unless all of the following hold. Each is
enforced by a `validation` block in `variables.tf` or a `precondition` in
`main.tf`, and each is *proved to reject* by a `run` block with
`expect_failures` in `tests/refusal.tftest.hcl`.

| Invariant | Enforced by | Proof |
|---|---|---|
| `environment == "test"` | `validation` | `refuses_environment_prod`, `refuses_environment_dev` |
| `subscription_id` ∈ `allowed_subscription_ids` (default `[]`) | `precondition` | `refuses_subscription_not_in_allowlist`, `refuses_empty_allowlist` |
| resource group starts `skd-autofde-test-` | `validation` | `refuses_unprefixed_resource_group`, `refuses_near_miss_prefix` |
| `enable_real_notification == false` | `validation` + `precondition` | `refuses_real_notification` |
| `enable_production_actuation == false` | `validation` + `precondition` | `refuses_production_actuation` |
| `enable_destructive_identity_action == false` | `validation` + `precondition` | `refuses_destructive_identity_action` |
| `run_id` non-empty | `validation` | `refuses_empty_run_id`, `refuses_whitespace_run_id` |
| `owner` / `expiry` tags present | `validation` + `precondition` | `refuses_empty_owner`, `refuses_malformed_expiry`, `refuses_tag_override_that_blanks_owner` |
| managed identity used | no opt-out exists | positive assertions in `tests/identity.tftest.hcl` |
| retention bounded (7–30 days) | `validation` + `precondition` | `refuses_unbounded_retention` |

The **default state is refusal**: `allowed_subscription_ids` defaults to
`[]`, so a plan with no operator input fails.

The active `az` CLI context is **never** read to infer a subscription.
`providers.tf` binds `subscription_id` from an explicit variable; nothing
here uses `azurerm_client_config` or `use_cli`. There is no `az` on this
machine, and the configuration does not depend on that being true.

## Topology

Isolated resource group → Log Analytics workspace (private ingest + private
query, bounded retention) → Sentinel onboarding + one synthetic detection
(disabled) → data collection endpoint for synthetic incident ingress (no
public network access) → user-assigned managed identity → `Reader` role
assignment scoped to the resource group only → Logic App response playbook
(disabled, user-assigned identity) → action group notification capture sink
(disabled, zero recipients) → private storage account + private container as
evidence sink (no shared access keys).

### Local precedent, disclosed

Across all 702 `.tf` files under `~`:

- `azurerm_log_analytics_workspace` — 14 uses, precedent exists
- managed identity as a `dynamic "identity"` toggle — precedent exists
- `azurerm_role_assignment` — 3 uses, precedent exists
- `azurerm_sentinel_*` — **zero uses, no local precedent**
- `azurerm_logic_app_*` — **zero uses, no local precedent**

The Sentinel and Logic App blocks are greenfield in this codebase. Their
argument shapes are checked only by `terraform validate` against the azurerm
`~> 3.90` schema and by mocked plans. Do not read the confidence earned by
the first three rows into the last two.

`run_id` is likewise a **new convention** — no IaC under `~` has one. The
nearest existing idiom, `random_string.suffix`, is deliberately not used: an
orphan sweep needs a value the operator already holds.

## Derived from

- `/Users/sac/praxis/deploy/azure/ma-case-study` — the only `*.tftest.hcl`
  under `~`. Source of the flat-root layout, `tests/` (not `tests/unit/`),
  `required_version >= 1.7.1`, `azurerm ~> 3.90`, `mock_provider` +
  `command = plan` + `assert{condition,error_message}`, `nullable = false`,
  and the three-layer lowercase-hyphen tag merge.
- `/Users/sac/yawl/terraform/variables.tf` — source of the `validation`
  idiom (`contains(...)`, `can(regex(...))`). praxis has none.
  **Not** copied: yawl's `CreatedAt = timestamp()` tag, which forces a
  perpetual diff on every plan. `tests/plan.tftest.hcl` asserts its absence.

## Running the checks

```bash
terraform -chdir=infra/azure/autofde-breach-clock fmt -check -recursive
terraform -chdir=infra/azure/autofde-breach-clock init -backend=false
terraform -chdir=infra/azure/autofde-breach-clock validate
terraform -chdir=infra/azure/autofde-breach-clock test
```

`-backend=false` matches the house CI convention
(`~/jotp/.github/workflows/infra-validation.yml:56`,
`~/erlmcp/.github/workflows/gcp-deploy.yml:59`). No `backend "azurerm"` is
declared here and none may be added — remote state would create a path to a
real apply.

From pytest:

```bash
uv run pytest tests/autofde/test_terraform_guards.py -q
```

That suite parses `terraform test` output per run name rather than checking
the exit code, so deleting a guard *and* its proof fails loudly instead of
shrinking the suite silently. It skips with
`UNSUPPORTED:TERRAFORM_ABSENT` when `terraform` is not on `PATH`.

**Never run** `terraform apply`, `terraform destroy`, or anything requiring
credentials from this directory.

## Files

| File | Role |
|---|---|
| `versions.tf` | core + provider pins; no backend |
| `providers.tf` | explicit `subscription_id`; no credential arguments |
| `variables.tf` | every safety invariant as a `validation` block |
| `locals.tf` | three-layer tag merge, refusal predicates |
| `main.tf` | topology + `precondition` guardrails |
| `outputs.tf` | no secrets; `refusal_posture` summary |
| `tests/plan.tftest.hcl` | happy-path topology and tags |
| `tests/identity.tftest.hcl` | managed identity, least privilege |
| `tests/refusal.tftest.hcl` | **the evidence** — each guard proved to reject |
| `tests/apply_smoke.tftest.hcl` | authored, never run; zero live `run` blocks |
| `scripts/orphan_sweep.sh` | authored, never run; keyed on `run` + `expiry` tags |

## See also

- `.claude/rules/standing-law.md` — the `ALIVE`/`BLOCKED`/`NOT_RUN`
  vocabulary used above.
- `.claude/rules/actuation-boundary.md` — why this repository computes and
  does not actuate.
