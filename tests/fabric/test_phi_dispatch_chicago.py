# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: real phi() output dispatched into the real solver-match filter.

Phase 2 of the phi -> dispatch line: Phase 1 (`phi.py`) already proved each closed
`RelationClass` encodes into a real, instantiated scikit-decide domain object. This
test proves the *next* real hop -- that the existing, unmodified compatibility-filter
dispatch (`autofde_lab.fabric.service.DecisionFabric.match()`'s own solver-matching
step, `ScikitDecideBackend.match_solvers()`, which is `autofde_lab.utils.match_solvers()`
under the hood) returns a real, non-empty `compatible_solvers` tuple for each of those
real domain instances.

No new dispatch code is written here. This only tests the existing real dispatch
against phi's real output, per the task boundary and
`.claude/rules/testing-chicago-style.md`: every domain instance is the real object
`phi()` constructs (`ReconcileDomain`, `GraphDomain`, `RCPSP`), and
`ScikitDecideBackend.match_solvers()` is called directly and for real -- no mock, no
stub, no patched registry. `_utils().match_solvers()` iterates the *actually
registered* solver entry points and calls each one's real `check_domain(domain)`.
"""

from __future__ import annotations

import os

import pytest

from autofde_lab import utils as autofde_lab_utils
from autofde_lab.fabric.backend import ScikitDecideBackend
from autofde_lab.fabric.phi import _ENCODERS, phi
from autofde_lab_planner.scanner.models import Anomaly, RelationClass


def _anomaly(**overrides) -> Anomaly:
    base = dict(
        kind="Deployment",
        object_name="web",
        namespace="default",
        relation_class="declared_vs_observed",
        field="replicas",
        observed="1",
        expected="3",
        detail="declared 3 replicas, observed 1 ready",
    )
    base.update(overrides)
    return Anomaly(**base)


# One real, representable (non-UNREPRESENTABLE) Anomaly per closed RelationClass
# entry -- each of these is asserted elsewhere (test_phi_chicago.py) to produce a
# real domain instance via phi(), not an UNREPRESENTABLE result.
_REPRESENTABLE_ANOMALIES: dict[RelationClass, Anomaly] = {
    "declared_vs_observed": _anomaly(
        relation_class="declared_vs_observed",
        object_name="web",
        namespace="default",
        observed="1",
        expected="3",
    ),
    "dangling_reference": _anomaly(
        relation_class="dangling_reference",
        kind="Ingress",
        object_name="checkout-ingress",
        namespace="shop",
        field="backend.service.name",
        observed="checkout-svc",
        expected=None,
        detail="Ingress references Service checkout-svc which does not exist",
    ),
    "insufficient_capability": _anomaly(
        relation_class="insufficient_capability",
        kind="Pod",
        object_name="worker-0",
        namespace="batch",
        field="cpu",
        observed="4",
        expected="2",
        detail="Pod requests 4 CPU against a 2 CPU node capacity",
    ),
    "aggregate_threshold": _anomaly(
        relation_class="aggregate_threshold",
        kind="ResourceQuota",
        object_name="team-quota",
        namespace="team-a",
        field="requests.cpu",
        observed="12",
        expected="8",
        detail="aggregate CPU requests 12 exceed quota threshold 8",
    ),
}


def test_fixture_covers_every_closed_relation_class():
    """Guard the fixture itself against drifting out of sync with the closed table."""
    assert set(_REPRESENTABLE_ANOMALIES.keys()) == set(_ENCODERS.keys())
    assert set(_ENCODERS.keys()) == set(RelationClass.__args__)


@pytest.mark.parametrize(
    "relation_class", sorted(_REPRESENTABLE_ANOMALIES), ids=sorted(_REPRESENTABLE_ANOMALIES)
)
def test_phi_output_dispatches_to_a_real_nonempty_compatible_solver_set(relation_class):
    """For each phi()-produced real domain instance, match_solvers() is non-empty.

    This is the real gap-detection assertion the task asks for: if
    `ScikitDecideBackend.match_solvers()` (i.e. `autofde_lab.utils.match_solvers()`
    run against the *actually registered* solver entry points) returns an empty list
    for any of these real domain instances, that is a real dispatch gap between phi's
    output and the existing compatibility filter -- reported here, not silently
    worked around.
    """
    anomaly = _REPRESENTABLE_ANOMALIES[relation_class]

    domain_instance = phi(anomaly)

    backend = ScikitDecideBackend()
    compatible_solvers = backend.match_solvers(domain_instance)

    assert compatible_solvers, (
        f"real phi() output for relation_class={relation_class!r} "
        f"(domain type {type(domain_instance).__name__}) matched zero registered "
        f"solvers via ScikitDecideBackend.match_solvers() -- a real dispatch gap "
        f"between phi's output and the existing compatibility filter"
    )
    # Every match must be a real solver type this repo actually registered, not a
    # coincidental truthy value.
    for solver_type in compatible_solvers:
        assert isinstance(solver_type, type)


class TestMatchSolversRanked:
    """Real coverage of ``match_solvers(ranked=True)``'s two real code paths.

    Chicago style: no mock/patch/monkeypatch of ``subprocess`` or of
    ``_resolve_cmca_rank_cli_bin``'s internals -- both sub-tests exercise the
    real function against a real filesystem state (the binary genuinely
    present, or the env genuinely pointed at a real nonexistent path).
    """

    def _representative_domain(self):
        anomaly = _REPRESENTABLE_ANOMALIES["declared_vs_observed"]
        return phi(anomaly)

    def test_ranked_true_binary_unavailable_falls_back_gracefully(self, monkeypatch):
        """cmca_rank_cli genuinely unresolvable -> ranked=True must not crash.

        This direction is always real regardless of environment: point
        CMCA_RANK_CLI_BIN at a real nonexistent path and unset BCINR_HOME so
        the default-root fallback also can't resolve a real binary.
        """
        monkeypatch.setenv(
            "CMCA_RANK_CLI_BIN", "/nonexistent/path/does-not-exist/cmca_rank_cli"
        )
        monkeypatch.delenv("BCINR_HOME", raising=False)

        domain_instance = self._representative_domain()
        result = autofde_lab_utils.match_solvers(domain_instance, ranked=True)

        assert result, "expected a non-empty ranked result (fallback to match order)"
        for solver_type, score in result:
            assert isinstance(solver_type, type)
            assert isinstance(score, int)
        # Fallback preserves match order and pairs it with 1-based rank position.
        unranked = autofde_lab_utils.match_solvers(domain_instance, ranked=False)
        assert [s for s, _ in result] == unranked
        assert [score for _, score in result] == list(range(1, len(unranked) + 1))

    def test_ranked_false_default_behaviour_is_unchanged(self):
        domain_instance = self._representative_domain()
        result = autofde_lab_utils.match_solvers(domain_instance)
        assert result
        for solver_type in result:
            assert isinstance(solver_type, type)

    @pytest.mark.skipif(
        autofde_lab_utils._resolve_cmca_rank_cli_bin() is None,
        reason=(
            "cmca_rank_cli binary not resolvable in this environment "
            "(checked CMCA_RANK_CLI_BIN and $BCINR_HOME/target/debug/cmca_rank_cli); "
            "ranked=True's optional binary-present path is skipped, not faked"
        ),
    )
    def test_ranked_true_binary_present_returns_all_matches_with_real_or_synthetic_scores(
        self,
    ):
        """Only runs when cmca_rank_cli is genuinely resolvable on this machine.

        Renamed from ``..._returns_real_shares``: that name was misleading --
        before the >8 pre-filter existed, this domain's 46 real matched
        candidates always exceeded cmca_rank_cli's N=8 limit (CMCA-108) and
        the test only ever proved the refusal/fallback path, never real
        shares. ``match_solvers`` now pre-filters to the top 8 before
        calling the CLI (see ``_prefilter_top_for_ranking``), so this test
        instead asserts the *documented* combined-path contract: all
        matches are still present in the result (none silently dropped),
        and every entry has a real cmca_rank_cli float share or the
        documented lower synthetic fallback score.
        See ``test_ranked_true_prefilters_and_exercises_real_success_path``
        for the assertion that the real subprocess success path fires.
        """
        domain_instance = self._representative_domain()
        unranked = autofde_lab_utils.match_solvers(domain_instance, ranked=False)
        result = autofde_lab_utils.match_solvers(domain_instance, ranked=True)

        # No match is ever dropped by ranked=True, regardless of >8 pre-filtering.
        assert len(result) == len(unranked)
        assert {s for s, _ in result} == set(unranked)

        for _, score in result:
            assert isinstance(score, (int, float))

    def test_ranked_true_prefilters_and_exercises_real_success_path(self):
        """New test: proves the real >8 pre-filter + real cmca_rank_cli success path.

        Before this fix, ranked=True on a >8-candidate domain always sent
        every candidate to cmca_rank_cli, which always refused (CMCA-108),
        so the real ranking success path was never exercised on real data.
        This test asserts, with real data and no mock/patch/monkeypatch of
        the subprocess boundary:

        (a) the pre-filter reduces what's sent to cmca_rank_cli to <=8
            candidates before the subprocess call (verified directly via
            ``_prefilter_top_for_ranking``, the same function
            ``match_solvers`` uses internally);
        (b) the real subprocess call succeeds -- ``_rank_via_cmca_rank_cli``
            returns a non-``None`` ranking for those <=8 candidates, i.e.
            the refusal path is not what fired;
        (c) the returned shares for the CLI-ranked candidates are real,
            distinct-ish floats from cmca_rank_cli -- not the unranked
            fallback's synthetic 1-based int ranks.

        Skipped, not faked, when either the binary or a real >8-candidate
        domain isn't available in this environment.
        """
        if autofde_lab_utils._resolve_cmca_rank_cli_bin() is None:
            pytest.skip(
                "cmca_rank_cli binary not resolvable in this environment "
                "(checked CMCA_RANK_CLI_BIN and $BCINR_HOME/target/debug/cmca_rank_cli)"
            )

        domain_instance = self._representative_domain()
        unranked = autofde_lab_utils.match_solvers(domain_instance, ranked=False)
        if len(unranked) <= autofde_lab_utils._CMCA_RANK_CLI_MAX_CANDIDATES:
            pytest.skip(
                f"this domain matched only {len(unranked)} candidates (<=8); "
                "the >8 pre-filter this test targets isn't exercised without "
                "a real >8-candidate domain"
            )

        # (a) real pre-filter reduces to <=8 before the subprocess call.
        top, rest = autofde_lab_utils._prefilter_top_for_ranking(unranked)
        assert len(top) == autofde_lab_utils._CMCA_RANK_CLI_MAX_CANDIDATES
        assert len(rest) == len(unranked) - autofde_lab_utils._CMCA_RANK_CLI_MAX_CANDIDATES
        assert set(top) | set(rest) == set(unranked)

        # (b) the real subprocess call on the pre-filtered <=8 succeeds --
        # not the >8 refusal path.
        ranked_via_cli = autofde_lab_utils._rank_via_cmca_rank_cli(top)
        assert ranked_via_cli is not None, (
            "cmca_rank_cli refused even after pre-filtering to "
            f"{autofde_lab_utils._CMCA_RANK_CLI_MAX_CANDIDATES} candidates -- "
            "the real success path did not fire"
        )
        assert len(ranked_via_cli) == len(top)

        # (c) real, distinct-ish float shares -- not synthetic 1-based ranks.
        cli_shares = [score for _, score in ranked_via_cli]
        for score in cli_shares:
            assert isinstance(score, float)
        assert len(set(cli_shares)) > 1, (
            "expected real cmca_rank_cli shares to differ across distinct "
            "candidates, not collapse to a single repeated value"
        )
        assert sorted(cli_shares) != list(range(1, len(cli_shares) + 1)), (
            "shares look like the unranked fallback's synthetic 1-based "
            "int ranks, not real cmca_rank_cli output"
        )

        # End-to-end: match_solvers(ranked=True) itself must reflect the
        # same real success path (real floats first, `rest` appended with
        # documented lower synthetic scores, nothing dropped).
        result = autofde_lab_utils.match_solvers(domain_instance, ranked=True)
        assert len(result) == len(unranked)
        assert {s for s, _ in result} == set(unranked)
        ranked_prefix = result[: len(top)]
        assert {s for s, _ in ranked_prefix} == set(top)
        for _, score in ranked_prefix:
            assert isinstance(score, float)
        tail = result[len(top) :]
        assert [s for s, _ in tail] == rest
        if tail:
            min_ranked_score = min(score for _, score in ranked_prefix)
            assert all(score < min_ranked_score for _, score in tail)
