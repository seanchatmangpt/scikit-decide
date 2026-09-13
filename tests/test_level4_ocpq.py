# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: the real wasm4pm OCPQ engine, called in-process.

Every collaborator here is real: a real ``run_real_trial`` driving the real
gymact actuation subprocess (the same fixture pattern
``tests/ecosystem/test_level4_ocel_vocabulary_chicago.py`` uses), the real
SQLite receipt ledger it writes, the real :func:`build_level4_ocel`, and the
real native ``wasm4pm`` PyO3 extension (``wasm4pm-bindings-py``, built via
``maturin build --release`` from ``wasm4pm/crates/wasm4pm-bindings-py``
against the real OCPQ engine in ``wasm4pm/src/ocpq_runtime.rs``). No mock,
stub, patch or monkeypatch appears in this file.

If the native extension is not importable (bindings not built/installed in
this environment), the whole module is skipped -- named and visible, never
silently substituted with a Python re-implementation of the engine.
"""

from __future__ import annotations

import pathlib

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial
from autofde_lab.hub.domain.gym_procedure.level4_ocel import build_level4_ocel
from autofde_lab.hub.domain.gym_procedure.level4_ocpq import (
    OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY,
    ActuationPostconditionVerdict,
    run_actuation_postcondition_query,
    wasm4pm_ocpq_available,
)

if not wasm4pm_ocpq_available():
    pytest.skip(
        "UNSUPPORTED: wasm4pm (wasm4pm-bindings-py native extension) is not "
        "importable in this environment; build it with `maturin build "
        "--release` in wasm4pm/crates/wasm4pm-bindings-py and install the "
        "wheel to exercise the real OCPQ engine",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def executed_trial(tmp_path_factory) -> pathlib.Path:
    """One real Level 4 trial: real probing, real planner federation, real
    gymact actuation subprocess, real receipts -- same construction as
    ``tests/ecosystem/test_level4_ocel_vocabulary_chicago.py``'s fixture of
    the same name, reused rather than re-implemented.
    """
    root = tmp_path_factory.mktemp("level4_ocpq")
    report = run_real_trial(
        3979297810, "resource_flow", {"target": 3, "capacity": 4, "mine_rate": 1}, root
    )
    if report.outcome != "EXECUTED":
        pytest.skip(
            f"UNSUPPORTED: trial did not reach actuation (outcome={report.outcome}); "
            "an actuation-free trial has no ActuationOpened events for this "
            "query to run over"
        )
    return pathlib.Path(report.evidence_dir)


def test_real_ocpq_engine_confirms_every_actuation_has_an_observed_postcondition(
    executed_trial: pathlib.Path,
) -> None:
    """The real query, the real engine, the real per-task result.

    A trial that reached ``EXECUTED`` ran gymact's real
    ``execute_verified``, which never opens an actuation without also
    running the independent postcondition check that produces
    ``PostconditionObserved`` later in the same trial -- so the real OCPQ
    engine, run over the real log this trial produced, is expected to
    return ``Allow`` with zero violations. The assertion is on the engine's
    own returned verdict, not on a Python re-count of the same events.
    """
    level4 = build_level4_ocel(executed_trial)
    assert "ActuationOpened" in level4.report.populated_event_types
    assert "PostconditionObserved" in level4.report.populated_event_types

    verdict = run_actuation_postcondition_query(level4)

    assert isinstance(verdict, ActuationPostconditionVerdict)
    assert verdict.query == OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY
    assert verdict.ocel_event_count > 0
    assert verdict.ocel_object_count > 0
    assert verdict.status == "Allow", (
        f"real OCPQ engine reported violations for a trial that reached "
        f"EXECUTED: {verdict.violations!r}"
    )
    assert verdict.violations == ()
    assert verdict.passed is True


def test_real_ocpq_engine_reports_a_real_violation_when_a_postcondition_is_missing(
    executed_trial: pathlib.Path,
) -> None:
    """The negative case, driven off the same real log -- not a synthetic one.

    Drop every ``PostconditionObserved`` event from the OCEL the query is
    run against (a real, if adversarial, OCEL 2.0 document -- the engine
    does not know or care that it was constructed by a test) and confirm
    the real engine reports ``Deny`` with a violation naming the actuation
    object, rather than passing silently. This is the engine's own
    detection at work, not an assertion invented in this test.
    """
    import json

    import wasm4pm

    level4 = build_level4_ocel(executed_trial)
    ocel_doc = level4.log.to_ocel2_json()
    ocel_doc["events"] = [
        e for e in ocel_doc["events"] if e["type"] != "PostconditionObserved"
    ]
    assert any(e["type"] == "ActuationOpened" for e in ocel_doc["events"])
    assert not any(e["type"] == "PostconditionObserved" for e in ocel_doc["events"])

    verdict_json = wasm4pm.evaluate_ocpq(
        json.dumps(ocel_doc), OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY
    )
    verdict = json.loads(verdict_json)

    assert verdict["status"] == "Deny"
    assert len(verdict["violations"]) > 0
    assert any("ActuationOpened" in v for v in verdict["violations"])
