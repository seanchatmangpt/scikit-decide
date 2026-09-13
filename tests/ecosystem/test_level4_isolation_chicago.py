# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style negative concurrency test: prove Level 4 trial isolation is real.

Hardening against a REAL prior incident (earlier Level 3 work): parallel
agents without per-trial isolation wrote to the same scratch filenames and
one run silently consumed another run's state. Asserting isolation is not
enough -- this module runs four REAL trials CONCURRENTLY, each a real
`RealBlindEnvironment` driving real subprocesses into gymact's own venv
against the real `cube_counter` provider, with DIFFERENT targets (2,3,4,5)
chosen so that contamination is *visible*: a leaked probe or a shared log
would land a counter value that no single trial's own config can produce.

No mocks, no fakes, no patching anywhere in this file -- real threads, real
subprocesses, real files on disk, assertions on final state.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    RealBlindEnvironment,
    skip_reason,
)
from autofde_lab.hub.domain.gym_procedure.level4_generator import Trial
from autofde_lab.hub.domain.gym_procedure.trial_isolation import (
    EvidenceDirContention,
    acquire_exclusive_evidence_dir,
    read_claim,
)

pytestmark = pytest.mark.skipif(skip_reason() is not None, reason=str(skip_reason()))

TARGETS = (2, 3, 4, 5)


def _run_one_trial(root: Path, target: int) -> dict:
    """One fully isolated trial: own Trial (uuid4 run_id + own dir), own
    exclusive claim, own RealBlindEnvironment, `target` real increments."""
    trial = Trial.new(seed=target, root=root)
    claim = acquire_exclusive_evidence_dir(trial.evidence_dir, owner=f"target={target}")
    try:
        env = RealBlindEnvironment(
            provider_key="cube_counter",
            config={"target": target},
            evidence_dir=trial.evidence_dir,
            claim=claim,  # this trial already holds the claim; don't self-collide
        )
        records = [env.try_action("increment") for _ in range(target)]
        return {
            "target": target,
            "run_id": trial.run_id,
            "claim_id": claim.claim_id,
            "evidence_dir": trial.evidence_dir,
            "episode_id": env.episode_id(),
            "records": records,
            "final_post": records[-1]["observed_post"],
        }
    finally:
        claim.release()


def test_four_concurrent_real_trials_stay_isolated(tmp_path: Path) -> None:
    root = tmp_path / "crown_runs"
    root.mkdir()

    with ThreadPoolExecutor(max_workers=len(TARGETS)) as pool:
        results = list(pool.map(lambda t: _run_one_trial(root, t), TARGETS))

    assert len(results) == len(TARGETS)

    # --- distinct evidence dirs, run_ids, episode_ids -------------------
    dirs = [r["evidence_dir"] for r in results]
    assert len({str(d) for d in dirs}) == len(TARGETS), dirs
    run_ids = [r["run_id"] for r in results]
    assert len(set(run_ids)) == len(TARGETS), run_ids
    episode_ids = [r["episode_id"] for r in results]
    assert all(e for e in episode_ids), episode_ids
    assert len(set(episode_ids)) == len(TARGETS), episode_ids

    for r in results:
        target = r["target"]
        log = r["evidence_dir"] / "probes.jsonl"
        assert log.is_file()
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]

        # --- only this trial's probes, by count AND by content ----------
        assert len(lines) == target, (target, lines)
        recs = [json.loads(ln) for ln in lines]
        assert [x["action"] for x in recs] == ["increment"] * target
        # Every record must be consistent with THIS trial's own config:
        # target field, and a counter walking exactly 0->1->...->target.
        for i, rec in enumerate(recs):
            assert rec["applicable"] is True, rec
            assert rec["observed_pre"]["target"] == target, rec
            assert rec["observed_post"]["target"] == target, rec
            assert rec["observed_pre"]["counter"] == i, rec
            assert rec["observed_post"]["counter"] == i + 1, rec

        # --- final state is what THIS trial's config implies -------------
        final = r["final_post"]
        assert final["counter"] == target, (target, final)
        assert final["target"] == target, (target, final)
        assert final["solved"] is True, (target, final)

    # Cross-check: the four final counters are exactly the four targets --
    # any cross-trial contamination would collapse or shift this set.
    assert sorted(r["final_post"]["counter"] for r in results) == sorted(TARGETS)


def test_shared_evidence_dir_is_refused_not_silently_interleaved(
    tmp_path: Path,
) -> None:
    """Adversarial case: two trials pointed at the SAME evidence_dir.

    `RealBlindEnvironment.__init__` uses ``mkdir(parents=True, exist_ok=True)``
    and would silently append both trials' probes into one probes.jsonl.
    The guard detects it instead.
    """
    shared = tmp_path / "shared_dir"

    first = acquire_exclusive_evidence_dir(shared, owner="trial-A")
    assert read_claim(shared)["owner"] == "trial-A"

    with pytest.raises(EvidenceDirContention) as excinfo:
        acquire_exclusive_evidence_dir(shared, owner="trial-B")
    assert "already claimed" in str(excinfo.value)
    assert "trial-A" in str(excinfo.value)

    # The first holder's claim is untouched by the refused second attempt.
    assert read_claim(shared)["claim_id"] == first.claim_id

    # And the directory is reusable only after an explicit release.
    first.release()
    assert read_claim(shared) is None
    second = acquire_exclusive_evidence_dir(shared, owner="trial-B")
    assert read_claim(shared)["owner"] == "trial-B"
    assert second.claim_id != first.claim_id
    second.release()


def test_silent_sharing_is_refused_by_the_constructor_itself(tmp_path: Path) -> None:
    """REGRESSION GUARD for a defect that was real and is now fixed.

    Before the fix, `RealBlindEnvironment.__init__` did
    `mkdir(parents=True, exist_ok=True)` and nothing else, so two
    environments built on one `evidence_dir` silently shared a single
    `probes.jsonl`. That was reproduced for real: two trials (target=2 and
    target=5) each doing one increment left ONE log holding records whose
    `observed_post.target` values were `[2, 5]` -- a verifier reading that
    log alone cannot attribute a record to a trial. That is exactly the
    Level 3 cross-trial contamination incident's shape.

    The claim is now taken inside `__init__`, so the SECOND construction
    raises instead of quietly interleaving. This test fails if anyone ever
    reintroduces the silent-sharing behaviour."""
    shared = tmp_path / "unguarded"
    first = RealBlindEnvironment("cube_counter", {"target": 2}, shared)
    assert first._log_path.parent == shared

    with pytest.raises(EvidenceDirContention) as excinfo:
        RealBlindEnvironment("cube_counter", {"target": 5}, shared)
    assert "already claimed" in str(excinfo.value)

    # And the log really does contain only the first trial's records.
    first.try_action("increment")
    recs = [
        json.loads(ln)
        for ln in first._log_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [r["observed_post"]["target"] for r in recs] == [2], recs
