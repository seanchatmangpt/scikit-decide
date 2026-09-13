from pathlib import Path

from autofde_lab.fabric.selection import (
    DecisionRegime,
    EmpiricalPlannerIndex,
    EvidenceStanding,
    PlannerReceipt,
    PlannerRequirements,
    ProblemSignature,
)
from autofde_lab.fabric.selection_store import SQLitePlannerEvidenceStore


def signature():
    return ProblemSignature(deterministic=True)


def receipt(wall: float = 1.0):
    return PlannerReceipt(
        signature_key=signature().key,
        planner_id="Astar",
        success=True,
        verified=True,
        standing=EvidenceStanding.ALIVE,
        wall_time_s=wall,
        quality=1.0,
    )


def registered_index():
    index = EmpiricalPlannerIndex(min_hot_receipts=3)
    index.register(PlannerRequirements("Astar", equals={"deterministic": True}))
    return index


def test_exact_replay_is_idempotent_but_distinct_runs_accumulate(tmp_path: Path):
    with SQLitePlannerEvidenceStore(tmp_path / "evidence.sqlite3") as store:
        assert store.append(receipt(), run_nonce="run-1")
        assert not store.append(receipt(), run_nonce="run-1")
        assert store.append(receipt(), run_nonce="run-2")
        assert store.count() == 2


def test_persistence_survives_process_boundary(tmp_path: Path):
    path = tmp_path / "evidence.sqlite3"
    with SQLitePlannerEvidenceStore(path) as store:
        store.append(receipt(1.25), run_nonce="run-1")
    with SQLitePlannerEvidenceStore(path) as store:
        rows = store.receipts(signature_key=signature().key)
        assert len(rows) == 1
        assert rows[0].wall_time_s == 1.25


def test_hydration_reconstructs_hot_standing_from_repeated_evidence(tmp_path: Path):
    path = tmp_path / "evidence.sqlite3"
    with SQLitePlannerEvidenceStore(path) as store:
        for i in range(3):
            store.append(receipt(1 + i / 10), run_nonce=f"run-{i}")
    index = registered_index()
    with SQLitePlannerEvidenceStore(path) as store:
        assert store.hydrate(index) == 3
    assert index.route(signature()).regime is DecisionRegime.HOT


def test_unverified_evidence_persists_but_cannot_heat_route(tmp_path: Path):
    bad = PlannerReceipt(
        signature_key=signature().key,
        planner_id="Astar",
        success=True,
        verified=False,
        standing=EvidenceStanding.ALIVE,
    )
    path = tmp_path / "evidence.sqlite3"
    with SQLitePlannerEvidenceStore(path) as store:
        for i in range(4):
            store.append(bad, run_nonce=f"run-{i}")
    index = registered_index()
    with SQLitePlannerEvidenceStore(path) as store:
        store.hydrate(index)
    assert index.route(signature()).regime is DecisionRegime.COLD


def test_file_store_uses_wal(tmp_path: Path):
    with SQLitePlannerEvidenceStore(tmp_path / "evidence.sqlite3") as store:
        mode = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
