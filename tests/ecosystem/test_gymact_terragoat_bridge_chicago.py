# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Ecosystem Chicago test: autofde-lab's candidate plan verified against a
real, independently-computed observation of the actual world state, via
`~/gymact`'s real actuation kernel.

This closes a specific, narrow loop -- not the whole "autofde-lab solves
gymact's cloud challenges" claim, which this file does NOT make (see
"Standing ceiling" below):

1. `TerraGoatRemediation` (this repo, `src/autofde_lab/hub/domain/terragoat`)
   parses the real `# <misconfiguration>` comments out of the real vendored
   `vendor/gyms/terragoat/terraform/alicloud/*.tf` files and computes a real
   candidate remediation plan with the real registered `Astar` solver --
   this is autofde-lab's own hand-written regex parser, independent of
   Terraform's own HCL parser.
2. `~/gymact`'s `TerraformPlanProvider` (a real actuation provider, driven
   as a real subprocess in gymact's own venv, never imported into this
   process) runs a real `terraform init -backend=false` + `terraform graph`
   against that SAME real directory, using Terraform's own HCL parser --
   completely independent of this repo's regex-based one. `graph`, not
   `plan`, is the real evidence surface used: `plan` cannot enumerate any
   resource for `terraform/alicloud` without a real Alibaba Cloud
   credential this provider must never be given (confirmed real this
   session -- see below), while `graph` is a pure static dependency-graph
   computation over the local HCL config that never contacts a provider.
3. This test asserts every real resource address autofde-lab's plan touches
   (`alicloud_oss_bucket.bad_bucket`, `alicloud_actiontrail_trail.fail`,
   `alicloud_db_instance.seeme`) appears in gymact's real, independently
   captured `terraform graph` stdout -- i.e. two independent real parsers
   of the same real files agree on which real resources exist.

Why `terraform/alicloud` and not `terraform/aws` (the file
`TerraGoatRemediation`'s own default constructor argument targets): AWS's
`.tf` files declare a real remote S3 backend requiring real credentials --
`gymact.gyms.terraform_plan`'s own module docstring (and its test module,
`~/gymact/tests/test_terraform_plan.py`) documents this exact reason for
choosing `terraform/alicloud` instead. This test's `TerraGoatRemediation`
instance is therefore constructed with the alicloud files explicitly, not
the class default.

Real cloud actuation (`terraform apply`) is structurally impossible through
`TerraformPlanProvider` -- there is exactly one capability, `plan`, and
`actuate()` has no dispatch branch for `apply`/`destroy` (per that module's
own docstring, verified by reading it this session). This test therefore
establishes "the plan is independently confirmed against real observed
world structure", never "the world was changed" -- exactly the
`request accepted != world changed != objective verified` distinction
`~/gymact/CLAUDE.md`'s own consequence law states, and exactly the
`this repo computes candidate plans; it does not actuate` boundary this
repo's own `CLAUDE.md` states.

Skips with a named blocker (never substitutes a fixture and proceeds) when:
`~/gymact` is not checked out, its `.venv` is absent, or neither
`terraform` nor `tofu` is on `PATH` -- matching this file's sibling crown
tests' discipline (`test_chatman_chain_chicago.py`).

Known architectural debt, stated so it does not drift unrecorded: this test
still calls `TerraGoatRemediation`, a HAND-WRITTEN domain that parses
`vendor/gyms/terragoat`'s `.tf` files with autofde-lab's own regex, listing
a specific gym's specific misconfiguration comments by hand. That is not
where this integration should end up. `~/gymact` already exposes a real,
generic `Capability`/semantic-profile surface per provider (see
`gymact.models.Capability`, `gymact.semantic`, and its PROF/SHACL profile
export) -- the production-ready shape is a domain SYNTHESIZED from a
provider's declared capabilities/observed state at runtime, not a
bespoke Python class per gym that this repo must hand-author and keep in
sync with the vendored checkout by hand. This test's cross-check (do
autofde-lab's plan targets match gymact's real observation) stays valid
under that redesign; only `TerraGoatRemediation`'s construction -- currently
"parse this repo's copy of the .tf files directly" -- would change to
"derive a domain from gymact's own materialized-environment capability
declaration for this provider", removing the hand-authored parser and the
per-gym domain module entirely. Filed here, not fixed here: that redesign
is a `~/gymact`-side capability-to-domain synthesis feature, out of scope
for this bridge test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.terragoat.terragoat_remediation import TerraGoatRemediation

REPO_ROOT = Path(__file__).resolve().parents[2]
ALICLOUD_DIR = REPO_ROOT / "vendor" / "gyms" / "terragoat" / "terraform" / "alicloud"

HOME = Path.home()
GYMACT = HOME / "gymact"
GYMACT_VENV_PYTHON = GYMACT / ".venv" / "bin" / "python"

_GYMACT_BRIDGE_SCRIPT = """
import asyncio
import json
import sys

from gymact.gyms.terraform_plan import TerraformPlanProvider


async def main(working_dir: str) -> dict:
    provider = TerraformPlanProvider()
    environment = await provider.materialize(
        scenario=None, config={"working_dir": working_dir}
    )
    try:
        # `graph` is real, independent evidence computed at materialize
        # time (a pure static HCL analysis, no provider auth involved) --
        # it is the correct surface here, not `plan`, which structurally
        # cannot enumerate any resource for terragoat/alicloud without real
        # cloud credentials this test must never supply (see
        # gymact.gyms.terraform_plan's own module docstring).
        observed = await environment.observe()
        return {"observed": observed}
    finally:
        await environment.teardown()


if __name__ == "__main__":
    result = asyncio.run(main(sys.argv[1]))
    print(json.dumps(result))
"""


def _terraform_or_tofu_available() -> bool:
    return shutil.which("terraform") is not None or shutil.which("tofu") is not None


def _alicloud_findings_present() -> bool:
    return ALICLOUD_DIR.is_dir() and any(ALICLOUD_DIR.glob("*.tf"))


def _skip_reason() -> str | None:
    if not GYMACT.is_dir():
        return f"BLOCKED:GYMACT_CHECKOUT_ABSENT: {GYMACT} does not exist"
    if not GYMACT_VENV_PYTHON.is_file():
        return f"BLOCKED:GYMACT_VENV_ABSENT: {GYMACT_VENV_PYTHON} does not exist"
    if not _terraform_or_tofu_available():
        return "BLOCKED:TERRAFORM_BINARY_ABSENT: neither 'terraform' nor 'tofu' is on PATH"
    if not _alicloud_findings_present():
        return f"BLOCKED:TERRAGOAT_ALICLOUD_ABSENT: {ALICLOUD_DIR} has no real .tf files"
    return None


@pytest.mark.skipif(_skip_reason() is not None, reason=str(_skip_reason()))
def test_autofde_lab_plan_targets_match_gymacts_real_terraform_plan_evidence(tmp_path):
    # Stage 1: autofde-lab's own candidate plan -- real domain, real Astar,
    # solved over the real vendored alicloud findings.
    alicloud_files = sorted(ALICLOUD_DIR.glob("*.tf"))
    domain = TerraGoatRemediation(terraform_file=alicloud_files, max_findings=None)
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan_finding_ids: list[str] = []
        for _ in range(20):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan_finding_ids.append(action)
            outcome = domain.step(action)
            obs = outcome.observation

    assert domain._is_goal(obs), f"A* did not clear every alicloud finding. Plan: {plan_finding_ids}"
    real_resources_touched = sorted({domain.describe_finding(fid).resource for fid in plan_finding_ids})
    assert real_resources_touched == [
        "alicloud_actiontrail_trail.fail",
        "alicloud_db_instance.seeme",
        "alicloud_oss_bucket.bad_bucket",
    ], real_resources_touched

    # Stage 2: gymact's real, independent actuation-provider evidence --
    # run as a real subprocess in gymact's own venv, never imported here.
    bridge_script = tmp_path / "gymact_terraform_plan_bridge.py"
    bridge_script.write_text(_GYMACT_BRIDGE_SCRIPT, encoding="utf-8")
    completed = subprocess.run(
        [str(GYMACT_VENV_PYTHON), str(bridge_script), str(ALICLOUD_DIR)],
        capture_output=True,
        text=True,
        cwd=str(GYMACT),
        timeout=180,
    )
    assert completed.returncode == 0, (
        f"gymact bridge subprocess failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    observed = result["observed"]

    # `graph` is a pure static HCL analysis -- no provider auth, no network
    # call -- so it must have run to real, deterministic completion
    # regardless of whether this environment has any cloud credentials.
    assert observed["init_attempted"] is True and observed["init_returncode"] == 0, observed
    assert observed["graph_attempted"] is True, observed
    assert observed["graph_returncode"] == 0, observed
    assert observed["graph_timed_out"] is False, observed

    graph_stdout = observed["graph_stdout"]
    for resource in real_resources_touched:
        assert resource in graph_stdout, (
            f"autofde-lab's candidate plan targets {resource!r}, but gymact's "
            f"real, independent `terraform graph` run over the same real "
            f"directory never mentions it. Real captured graph stdout:\n{graph_stdout}"
        )
