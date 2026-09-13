#!/usr/bin/env python3
"""Repo-wide cheat-pattern lint: failure points are honest, mocks are not.

Ported from ~/mfw/scripts/lint.py, which catches hollow Rust constructs and
hedge prose. Two things are added here.

First, Python equivalents of the hollow constructs -- this repo is mostly
Python, and `raise NotImplementedError` is the same claim as `todo!()`.

Second, and the reason this exists now: **mocks**. The Azure adapter work
proceeds with no subscription available, which is exactly the condition that
produces code that goes green without exercising anything.

    A failure point is honest: a typed refusal, a named blocker, a skip that
    states its exact reason.
    A mock is not: it turns an unexercised path green.

Chicago testing runs the real components for its scope. For infrastructure
that means real Terraform. `mock_provider "azurerm" {}` validates your own
`precondition` blocks; it cannot falsify a wrong resource schema, a bad KQL
query, insufficient RBAC, or a quota limit. That is a configuration-guard
check, not an integration test, and this lint says so out loud.

Unlike the mfw original, `tests/` is NOT excluded. A mock in a test is the
case this exists to find; excluding tests would make the whole scan vacuous.

Exit code is 1 if any scan finds anything. That is expected on the first run.
"""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Narrow and justified. A broad exclusion is how this control dies quietly.
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "target",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".terraform",
    "sdk",  # cpp/sdk: vendored pybind11, PEGTL, nlohmann/json
    "deps",
    "vendors",
    # Outside source. Scoping what is under test -- NOT suppressing findings
    # inside it. Every finding these dropped was inspected first, and the
    # delta is recorded rather than assumed:
    #
    #   docs/      8  -- 6 are wip-followup-plans.md prose *describing*
    #                    NotImplementedError branches; 1 is autodoc.py:195
    #                    matching the pattern inside a string literal; 1 is
    #                    KNOWN_LIMITATIONS.md:49 "Real Azure apply was never
    #                    run", i.e. the lint flagging an honest disclosure.
    #   notebooks/ 4  -- all `dummy_cost_when_already_schedule`, a real RCPSP
    #                    domain parameter, not a test double.
    #   examples/  2  -- `raise NotImplementedError()` in demo code.
    #
    # `src/`, `tests/`, `infra/`, `scripts/`, `ontology/` and `.github/` stay
    # in scope. In particular src/skdecide/{hub,builders} keeps its 152
    # inherited hollow findings: those are source, and they belong in the
    # KNOWN_LIMITATIONS baseline, not in this set.
    #
    # Stated trade: markdown was added to the scanned suffixes specifically to
    # reach prose evasions, and `docs/` is where prose lives. Excluding it
    # narrows the reach of `hedge`, `deferred_phase` and `predicted_standing`
    # to root-level and in-tree markdown only. That is a real reduction in
    # coverage, taken deliberately, not a coincidence of the file walk.
    "docs",
    "notebooks",
    "examples",
    "binder",
}

# Files whose whole purpose is to describe the patterns -- including this one.
EXCLUDED_FILE_NAMES = {"lint_cheat_patterns.py", "lint.py"}

SCANNED_SUFFIXES = {
    ".py",
    ".rs",
    ".tf",
    ".hcl",
    ".sh",
    ".toml",
    ".yml",
    ".yaml",
    ".js",
    ".ts",
    # Markdown is scanned deliberately. It was omitted in the first revision,
    # and `deferred_phase` and `predicted_standing` both reported ALIVE as a
    # result -- not because the repo was clean, but because the detector could
    # not see the files where those patterns live. A green that comes from not
    # looking is the vacuous pass this lint exists to prevent.
    ".md",
    ".ttl",
    ".rq",
}

SCANS: dict[str, re.Pattern[str]] = {
    # An unfinished construction asserted as if it were a design.
    "hollow": re.compile(
        r"\b(unimplemented!\(\)"
        r"|todo!\(\)"
        r'|panic!\(\s*"not implemented"'
        r"|raise NotImplementedError"
        r"|pass\s+#\s*(TODO|FIXME|XXX)"
        r"|#\s*(TODO|FIXME|XXX):?\s*implement)"
    ),
    # Prose that discloses an unfinished construction instead of a typed
    # obligation. Verbatim from mfw, plus two this repo has produced.
    "hedge": re.compile(
        r"(in a real implementation|for now,? (we('ll)?|this)|"
        r"temporary workaround|this is a placeholder|stub implementation|"
        r"not yet implemented|will be replaced|production implementation would|"
        r"in production,? (we|this)|real implementation would)",
        re.IGNORECASE,
    ),
    # A fake success. Note this deliberately does NOT match `monkeypatch`
    # alone: monkeypatch used to REMOVE capability (scrubbing HOME/PATH to
    # prove a refusal fires) is the honest shape and must keep passing.
    # What is caught is the fake-success shape.
    #
    "mock": re.compile(
        r"\b(unittest\.mock"
        r"|from unittest import mock"
        r"|MagicMock|AsyncMock|NonCallableMock"
        r"|@patch\b|mock\.patch|mocker\."
        r"|return_value\s*=|side_effect\s*="
        r"|requests_mock|responses\.add|vcr\.use_cassette"
        r"|\bfake_[a-z_]+|\bdummy_[a-z_]+|[a-z_]+_stub\b)"
    ),
    # Terraform's own mocking surface. A green `terraform test` under
    # mock_provider proves the config's preconditions, not that Azure would
    # accept the config.
    "terraform_mock": re.compile(
        r"\b(mock_provider|mock_resource|mock_data"
        r"|override_resource|override_data|override_module)\b"
    ),
    # ---------------------------------------------------------------
    # The classes below are NOT borrowed from mfw or from general practice.
    # They were derived by auditing this session's own output for the moves
    # used to avoid implementing something. Each has a real instance in this
    # repository, cited.
    # ---------------------------------------------------------------
    #
    # A file exists, is committed, is counted as progress, and cannot run.
    # Real instance: infra/azure/autofde-breach-clock/tests/apply_smoke.tftest.hcl
    # ships with every `run` block commented out; the CI T2/T3 lanes are
    # `workflow_dispatch` with no schedule; scripts/orphan_sweep.sh has never
    # been executed against anything.
    "authored_never_run": re.compile(
        r"(AUTHORED,? (BUT )?NEVER RUN|authored but never run"
        r"|never (been )?(executed|run)\b"
        r"|#\s*run\s+\"|//\s*run\s+\""
        r"|workflow_dispatch:\s*$"
        r"|if\s+False\b|if\s+0\s*:)",
        re.IGNORECASE,
    ),
    # Work pushed to a future pass that has no owner and no date.
    # Real instance: this repo's plan carried 12 phases; 5 were dispatched.
    # "Phase 2 -- the namespace, atomically (a later, separate pass)".
    "deferred_phase": re.compile(
        r"(a later,? separate pass|later pass|follow-on,? not this pass"
        r"|not this pass|deferred to|defer(red)? until"
        r"|out of scope for now|in a (later|future) (pass|phase|release)"
        r"|left for (later|future)|to be (done|built|implemented) later)",
        re.IGNORECASE,
    ),
    # A mapping asserted as policy with nothing computing it. Honest to
    # label, still not an implementation.
    # Real instance: src/autofde_lab/agent/faults.py DECLARED_MAPPING_ONLY --
    # 6 of 11 fault outcomes have no mechanism behind them.
    "declared_not_implemented": re.compile(
        r"(DECLARED_MAPPING_ONLY|declared mapping"
        r"|declared but not implemented|vocabulary ahead of its evidence"
        r"|no mechanism behind|policy only,? no mechanism)",
        re.IGNORECASE,
    ),
    # A standing claim written before the run that would establish it. The
    # hedge ("predicted, not claimed") does not survive being quoted, and in
    # this session it did not: rows from an expected-standing table were read
    # back as achieved results.
    "predicted_standing": re.compile(
        r"(expected standing|predicted standing|predicted,? not claimed"
        r"|should be ALIVE|expected at milestone|anticipated standing"
        r"|will be ALIVE|would be ALIVE)",
        re.IGNORECASE,
    ),
    # An exemption, allowlist, or skip added to a check AFTER it fired.
    # Real instance: `_is_abstract_method()` was added to this very file to
    # hide 129 of 144 hollow findings, then reverted.
    "suppressed_finding": re.compile(
        r"(#\s*(noqa|type:\s*ignore|nosec|pragma:\s*no cover)"
        r"|baseline file|grandfather|known[- ]failures? list"
        r"|allowlist(ed)? (because|since)|xfail\(|--continue-on-error)",
        re.IGNORECASE,
    ),
}

# Honest constructs. A line matching one of these is never a finding, or the
# lint would punish exactly the behaviour it exists to reward.
EXEMPT = re.compile(
    r"(Refusal\(|RefusalCode\.|AZ-\d{3}-|BLOCKED:|NOT_RUN|UNSUPPORTED:"
    r"|pytest\.skip\(|pytest\.importorskip\(|pytest\.xfail\("
    r"|expect_failures)"
)


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for filename in filenames:
            if filename in EXCLUDED_FILE_NAMES:
                continue
            path = Path(dirpath, filename)
            if path.suffix in SCANNED_SUFFIXES:
                yield path


def scan_file(relpath: str):
    """Run every pattern against one file. Runs in a worker process.

    There is deliberately NO exemption mechanism beyond EXEMPT, which lists
    honest constructs (typed refusals, named blockers, reasoned skips).

    An earlier revision of this file added `_is_abstract_method()` to hide
    `raise NotImplementedError` in abstract methods, on the reasoning that
    the idiom is correct Python. It is correct Python, and it is still a
    hollow point: the method has no body. That edit was made on seeing 144
    findings and wanting a smaller number, which is the precise behaviour
    this lint exists to catch. It was reverted.

    Inherited hollow constructs are recorded as a baseline in
    docs/release/KNOWN_LIMITATIONS.md, where they stay visible and countable.
    They are not suppressed in the detector.
    """
    path = REPO_ROOT / relpath
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    findings = []
    for name, pattern in SCANS.items():
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not pattern.search(line):
                continue
            if EXEMPT.search(line):
                continue
            findings.append((name, relpath, lineno, line.strip()[:160]))
    return findings


def main() -> int:
    relpaths = [str(p.relative_to(REPO_ROOT)) for p in iter_files(REPO_ROOT)]

    # Anti-vacuity: the mfw original can pass by walking zero files. An
    # over-broad exclusion must show up as a shrinking number, not a silent
    # green, so the count is asserted and then printed on every line.
    assert len(relpaths) > 100, (
        f"scanned only {len(relpaths)} files -- an exclusion is too broad, "
        "and a lint that walks nothing passes vacuously"
    )

    findings_by_scan: dict[str, list[tuple[str, int, str]]] = {n: [] for n in SCANS}
    with ProcessPoolExecutor() as pool:
        for file_findings in pool.map(scan_file, relpaths, chunksize=64):
            for name, relpath, lineno, line in file_findings:
                findings_by_scan[name].append((relpath, lineno, line))

    exit_code = 0
    n = len(relpaths)
    for name, findings in findings_by_scan.items():
        if findings:
            for relpath, lineno, line in findings:
                print(f"{relpath}:{lineno}: {line}")
            print(f"BUILD_BROKEN: {len(findings)} {name} finding(s) across {n} files")
            exit_code = 1
        else:
            print(f"ALIVE: no {name} constructs found across {n} files")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
