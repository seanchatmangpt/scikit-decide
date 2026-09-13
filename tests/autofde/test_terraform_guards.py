"""Chicago-style guard tests for infra/azure/autofde-breach-clock.

These shell out to the real ``terraform`` binary and assert on its real
output. They do not check exit code alone: a ``terraform test`` run can exit
0 while a refusal case silently stopped refusing (for example if a
``validation`` block were deleted and its ``run`` block deleted alongside
it). So the per-run PASS lines are parsed by name.

Standing vocabulary used in skip reasons follows ``.claude/rules/standing-law.md``:
``UNSUPPORTED:TERRAFORM_ABSENT`` when the binary is not on PATH.

The apply tier is deliberately untested here. It is ``NOT_RUN`` with two
independent blockers -- ``BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION`` and
``BLOCKED:AZURE_CLI_ABSENT`` -- recorded in
``infra/azure/autofde-breach-clock/tests/apply_smoke.tftest.hcl``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TF_DIR = REPO_ROOT / "infra" / "azure" / "autofde-breach-clock"

TERRAFORM = shutil.which("terraform")

pytestmark = pytest.mark.skipif(
    TERRAFORM is None,
    reason="UNSUPPORTED:TERRAFORM_ABSENT - terraform is not on PATH",
)

# Every refusal case that must be proved to actually refuse. If a guard is
# removed from the HCL, its run block disappears and this list fails loudly
# rather than the suite quietly shrinking.
REQUIRED_REFUSAL_RUNS = (
    "refuses_environment_prod",
    "refuses_environment_dev",
    "refuses_subscription_not_in_allowlist",
    "refuses_empty_allowlist",
    "refuses_non_guid_subscription",
    "refuses_unprefixed_resource_group",
    "refuses_near_miss_prefix",
    "refuses_real_notification",
    "refuses_production_actuation",
    "refuses_destructive_identity_action",
    "refuses_empty_run_id",
    "refuses_whitespace_run_id",
    "refuses_empty_owner",
    "refuses_malformed_expiry",
    "refuses_tag_override_that_blanks_owner",
    "refuses_tag_override_that_blanks_run",
    "refuses_unbounded_retention",
    "refuses_malformed_project_name",
)

REQUIRED_PLAN_RUNS = (
    "topology_and_guards",
    "mandatory_tags",
    "no_perpetual_diff_tag",
    "managed_identity_is_used",
    "role_assignment_is_least_privilege",
    "no_credential_material_is_output",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [TERRAFORM, f"-chdir={TF_DIR}", *args],
        capture_output=True,
        text=True,
        timeout=900,
    )


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


@pytest.fixture(scope="module")
def initialized() -> None:
    """``terraform init -backend=false``.

    ``-backend=false`` matches the house CI convention
    (``~/jotp/.github/workflows/infra-validation.yml``,
    ``~/erlmcp/.github/workflows/gcp-deploy.yml``). No backend block exists
    in this configuration and none may be added.
    """
    proc = _run("init", "-backend=false")
    if proc.returncode != 0:
        pytest.skip(
            "BLOCKED:PROVIDER_DOWNLOAD_FAILED - terraform init -backend=false "
            f"exited {proc.returncode}: {_strip_ansi(proc.stderr)[:2000]}"
        )


@pytest.fixture(scope="module")
def test_output(initialized: None) -> str:
    proc = _run("test")
    return _strip_ansi(proc.stdout + proc.stderr)


def test_no_backend_block_is_declared() -> None:
    """A remote backend would create a path to a real apply. There is none."""
    for tf_file in TF_DIR.glob("*.tf"):
        body = tf_file.read_text()
        assert not re.search(r"^\s*backend\s+\"", body, re.MULTILINE), (
            f"{tf_file} declares a backend block; this configuration must never "
            "acquire remote state."
        )


def test_no_az_cli_dependency_in_terraform_config() -> None:
    """The active ``az`` context must never be read to infer a subscription."""
    for tf_file in TF_DIR.glob("*.tf"):
        body = tf_file.read_text()
        assert "use_cli" not in body, f"{tf_file} references azurerm use_cli."
        assert "azurerm_client_config" not in body, (
            f"{tf_file} reads azurerm_client_config, which would infer the "
            "subscription from the ambient CLI context."
        )


def test_subscription_allowlist_defaults_to_empty() -> None:
    """The default state of this configuration is refusal."""
    body = (TF_DIR / "variables.tf").read_text()
    match = re.search(
        r"variable\s+\"allowed_subscription_ids\"\s*\{(.*?)\n\}",
        body,
        re.DOTALL,
    )
    assert match, "allowed_subscription_ids variable not found"
    assert re.search(r"default\s*=\s*\[\]", match.group(1)), (
        "allowed_subscription_ids must default to [] so a plan with no "
        "operator input refuses."
    )


def test_apply_smoke_has_no_live_run_blocks() -> None:
    """The apply-tier file is authored, never run."""
    body = (TF_DIR / "tests" / "apply_smoke.tftest.hcl").read_text()
    live = [
        line
        for line in body.splitlines()
        if re.match(r"^\s*run\s+\"", line) and not line.lstrip().startswith("#")
    ]
    assert live == [], (
        "apply_smoke.tftest.hcl must contain zero live run blocks: "
        "NOT_RUN, BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION and "
        f"BLOCKED:AZURE_CLI_ABSENT. Found: {live}"
    )


def test_terraform_fmt_is_clean(initialized: None) -> None:
    proc = _run("fmt", "-check", "-recursive")
    assert proc.returncode == 0, _strip_ansi(proc.stdout + proc.stderr)


def test_terraform_validate_succeeds(initialized: None) -> None:
    proc = _run("validate")
    combined = _strip_ansi(proc.stdout + proc.stderr)
    assert proc.returncode == 0, combined
    assert "The configuration is valid" in combined, combined


def test_terraform_test_overall_success(test_output: str) -> None:
    assert "Success!" in test_output, test_output
    assert re.search(r"\b0 failed\b", test_output), test_output


def _runs_not_passing(names: tuple[str, ...], test_output: str) -> list[str]:
    return [
        n
        for n in names
        if not re.search(rf'run "{re.escape(n)}"\.\.\. pass', test_output)
    ]


def test_every_refusal_case_actually_refuses(test_output: str) -> None:
    """Assert every named refusal run exists AND passed.

    Passing, for these runs, means Terraform produced the expected failure --
    each carries ``expect_failures``. Absence of the line is a failure: it
    means the guard's proof was deleted, which is exactly the regression a
    bare exit-code check would miss.

    Collapsed from a per-run parametrize. The distinctness of each falsifier is
    carried by ``REQUIRED_REFUSAL_RUNS`` itself (which
    ``test_every_refusal_run_in_hcl_is_listed_here`` cross-checks against the
    HCL), not by pytest item count; missing runs are accumulated so the message
    names every guard whose proof vanished, not just the first.
    """
    missing = _runs_not_passing(REQUIRED_REFUSAL_RUNS, test_output)
    assert not missing, (
        f"refusal cases did not report pass in terraform test output: {missing}"
        f"\n{test_output}"
    )


def test_every_positive_case_passes(test_output: str) -> None:
    missing = _runs_not_passing(REQUIRED_PLAN_RUNS, test_output)
    assert not missing, f"runs did not report pass: {missing}\n{test_output}"


def test_every_refusal_run_in_hcl_is_listed_here() -> None:
    """Guard against the guard list drifting behind the HCL."""
    body = (TF_DIR / "tests" / "refusal.tftest.hcl").read_text()
    in_hcl = set(re.findall(r'^run\s+"(refuses_[a-z0-9_]+)"', body, re.MULTILINE))
    assert in_hcl == set(REQUIRED_REFUSAL_RUNS), (
        "REQUIRED_REFUSAL_RUNS has drifted from refusal.tftest.hcl. "
        f"only in HCL: {sorted(in_hcl - set(REQUIRED_REFUSAL_RUNS))}; "
        f"only in python: {sorted(set(REQUIRED_REFUSAL_RUNS) - in_hcl)}"
    )
