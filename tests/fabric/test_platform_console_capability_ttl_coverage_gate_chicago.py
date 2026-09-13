"""Chicago-style durable regression gate on TTL coverage of the real
platform-console DO-class capability surface.

This is deliberately a *different* test from
test_platform_console_capability_ttl_coverage_chicago.py, which asserts
"no TTL individual is drift" (title -> real referent) and intentionally
does not gate on a coverage percentage. This file gates the other
direction: real surface -> TTL title. Revenue-generating swarms ship new
capabilities into platform-console continuously (three new approval
actions -- personnel.attestation.record, source-escrow.snapshot,
pentest.finding.resolve -- appeared between two runs on 2026-08-17 alone),
so a coverage number measured once is a snapshot, not a durable property.
This test re-measures it, for real, on every run.

No mocking: the real report comes from scripts/ttl_capability_coverage.py,
which parses the real TTL with rdflib and greps the real platform-console
source tree. The only "fake" input here is the known-gaps allowlist file,
which is itself real (committed, git-tracked, human-reviewable) -- not a
test double for anything.

Behavior:
  - Always prints the real, current coverage percentage and the real,
    current unmodeled-capability list, every run, in test output (not just
    on failure) -- so a human running pytest -v -s sees the number without
    needing this test to fail first.
  - If every unmodeled capability is present in the known-gaps allowlist,
    the test PASSES (an honest, disclosed exception is not the same as an
    undetected regression).
  - If any unmodeled capability is NOT in the allowlist, the test FAILS
    with a message that lists exactly which capability names need either
    TTL modeling or an allowlist entry -- actionable, not just a bare
    assertion failure.
  - If the real TTL or real platform-console checkout isn't available on
    this machine, the test is skipped -- named and visible, never a
    silent pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ttl_capability_coverage as cov  # noqa: E402

KNOWN_GAPS_PATH = Path(
    "/Users/sac/chatman-ecosystem/ontology/ttl-coverage-known-gaps.txt"
)

TTL_AVAILABLE = cov.TTL_PATH.exists()
PLATFORM_CONSOLE_AVAILABLE = (
    cov.APPROVAL_WORKFLOW_TS.exists() and cov.CASTLE_TS.exists() and cov.K8S_TS.exists()
)

pytestmark = pytest.mark.skipif(
    not (TTL_AVAILABLE and PLATFORM_CONSOLE_AVAILABLE),
    reason=(
        f"real TTL ({cov.TTL_PATH}) or real platform-console checkout "
        f"({cov.APP_ROOT}) not available on this machine -- named skip, "
        "not a silent mock substitution"
    ),
)


def parse_known_gaps(path: Path) -> dict[str, str]:
    """Real parse of the real, git-committed known-gaps allowlist file.
    Returns {capability_name: reason}. Missing file == empty allowlist
    (not an error -- the file is optional infrastructure, not a
    hidden dependency)."""
    if not path.exists():
        return {}
    gaps: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "--" in line:
            name, _, reason = line.partition("--")
            gaps[name.strip()] = reason.strip()
        else:
            gaps[line] = ""
    return gaps


@pytest.fixture(scope="module")
def report() -> dict:
    return cov.build_report().to_dict()


@pytest.fixture(scope="module")
def known_gaps() -> dict[str, str]:
    return parse_known_gaps(KNOWN_GAPS_PATH)


def test_known_gaps_file_entries_are_real_allowlist_lines(known_gaps: dict[str, str]) -> None:
    # Sanity on the allowlist parse itself: every kept key is non-empty and
    # not a comment/blank leaking through.
    for name in known_gaps:
        assert name
        assert not name.startswith("#")


def test_ttl_coverage_gate(report: dict, known_gaps: dict[str, str]) -> None:
    surface = report["total_real_do_capability_surface"]
    modeled = report["modeled_in_ttl_count"]
    unmodeled = report["unmodeled_capabilities"]
    ratio = report["coverage_ratio"]

    # Always-visible real numbers -- printed every run, not just on failure.
    print(
        f"\nreal TTL coverage: {modeled}/{surface} = {ratio:.1%} "
        f"({len(unmodeled)} unmodeled capability(ies) in current scan)"
    )
    if unmodeled:
        print(f"unmodeled capabilities: {unmodeled}")
    if known_gaps:
        print(f"known-gaps allowlist ({KNOWN_GAPS_PATH}): {known_gaps}")

    unexplained = [name for name in unmodeled if name not in known_gaps]

    if unexplained:
        allowlisted = [name for name in unmodeled if name in known_gaps]
        lines = [
            f"TTL coverage gate FAILED: {len(unexplained)} of {surface} real "
            f"platform-console capabilities have no ce:Capability individual "
            f"in {cov.TTL_PATH} and are not in the known-gaps allowlist "
            f"({KNOWN_GAPS_PATH}).",
            "",
            "Capabilities needing TTL modeling (or an honest known-gaps entry):",
        ]
        lines.extend(f"  - {name}" for name in unexplained)
        if allowlisted:
            lines.append("")
            lines.append("(already honestly allowlisted, not counted as failures):")
            lines.extend(f"  - {name}: {known_gaps[name]}" for name in allowlisted)
        pytest.fail("\n".join(lines))

    # Every real gap (if any) is disclosed. This is the honest pass path:
    # either coverage is 100%, or 100% of the gap is named and reasoned in
    # a git-committed file a human reviewed.
    assert True
