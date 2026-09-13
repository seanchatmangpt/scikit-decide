"""Chicago-style drift detector: every ce:Capability individual in the
real platform-console-capabilities.ttl file must correspond to a real,
still-shipping capability in platform-console's actual source tree.

No mocking anywhere in this file: the TTL is parsed for real with
rdflib against the real file on disk, and the "real DO-capability
surface" is computed by scripts/ttl_capability_coverage.py's real
regex/AST-adjacent scan of the real platform-console source tree
(lib/approval-workflow.ts's ACTIONS_REQUIRING_APPROVAL, lib/castle.ts's
AllowedCastleVerbId union, and app/api/**/route.ts files that call a
real mutating lib/k8s.ts function). If either the TTL file or the
platform-console checkout is missing, the test is skipped -- named and
visible, never silently faked.

This test intentionally does NOT assert a coverage-percentage threshold
(4/40-ish is real and would immediately fail any nontrivial floor, and
the whole point of this detector is to report that honestly). Instead it
asserts the actually meaningful, real invariant: no TTL individual is
drift -- i.e. every ce:Capability's dcterms:title must resolve to a real
name in the current capability surface. A title with no real referent
means either the capability was renamed/removed in code and the TTL
was never updated, or the TTL individual was authored with the wrong
name to begin with -- both are real bugs this test is designed to catch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ttl_capability_coverage as cov  # noqa: E402

TTL_AVAILABLE = cov.TTL_PATH.exists()
PLATFORM_CONSOLE_AVAILABLE = cov.APPROVAL_WORKFLOW_TS.exists() and cov.CASTLE_TS.exists() and cov.K8S_TS.exists()

pytestmark = pytest.mark.skipif(
    not (TTL_AVAILABLE and PLATFORM_CONSOLE_AVAILABLE),
    reason=(
        f"real TTL ({cov.TTL_PATH}) or real platform-console checkout "
        f"({cov.APP_ROOT}) not available on this machine -- named skip, "
        "not a silent mock substitution"
    ),
)


@pytest.fixture(scope="module")
def report() -> dict:
    return cov.build_report().to_dict()


def test_ttl_has_at_least_the_known_individuals(report: dict) -> None:
    # Sanity: the real TTL file really parses and really has individuals.
    assert report["ttl_individual_count"] >= 1
    assert len(report["ttl_titles"]) == report["ttl_individual_count"]


def test_real_do_capability_surface_is_nonempty(report: dict) -> None:
    # The real scan of approval-workflow.ts / castle.ts / route.ts must
    # find real capabilities -- a zero here means the scan itself broke,
    # not that platform-console has no DO-class surface.
    assert report["total_real_do_capability_surface"] > 0
    assert report["approval_action_count"] > 0
    assert report["castle_verb_count"] > 0
    assert report["mutating_route_count"] > 0


def test_no_ttl_individual_is_drift(report: dict) -> None:
    """The real, meaningful assertion: every ce:Capability's dcterms:title
    must resolve to a name that is still real in code (an
    ACTIONS_REQUIRING_APPROVAL entry, an ALLOWED_CASTLE_VERBS id, or a
    mutating route). A non-empty drift list means the TTL is stale or
    was authored with a name that never matched the real surface --
    catch it here, not in a later audit.
    """
    drift = report["ttl_drift_candidates_no_real_referent"]
    if drift:
        pytest.fail(
            "TTL individuals with no matching real capability in code "
            f"(stale or misnamed -- fix the TTL title or the code "
            f"reference): {drift}"
        )


def test_coverage_ratio_is_reported_honestly(report: dict) -> None:
    # Not a threshold assertion -- just proves the ratio is computed from
    # the real counts above it (modeled/surface), not fabricated.
    surface = report["total_real_do_capability_surface"]
    modeled = report["modeled_in_ttl_count"]
    assert surface > 0
    expected_ratio = modeled / surface
    assert report["coverage_ratio"] == pytest.approx(expected_ratio)
    # Document the real, current gap as of this test run so a future
    # change to either the TTL or the code surface is visible in the
    # pytest summary rather than silently drifting further.
    print(
        f"\nreal coverage: {modeled}/{surface} = {report['coverage_ratio']:.1%}; "
        f"unmodeled: {len(report['unmodeled_capabilities'])}"
    )
