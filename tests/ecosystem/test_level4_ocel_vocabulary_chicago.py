# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the Level 4 OCEL chain vocabulary.

Every collaborator here is real: a real ``run_real_trial`` driving the real
gymact actuation subprocess, the real SQLite ledger it writes, the real
rdflib Turtle parser, the real :class:`autofde_lab.ocel.log.OcelLog`
validators, and the real published OCEL 2.0 JSON Schema (loaded from
``tests/ocel/test_ocel2_conformance.py``, not re-typed here -- a second copy
is a second thing to drift). No mock, stub, patch or monkeypatch appears in
this file.

The question under test is the one that was previously unanswerable:
**did the execution conform to the committed solution?** Before this module,
``commitment.ttl`` and ``episode.ocel.json`` shared no identifier in either
direction, so the two artifacts could only be related by their being in the
same directory. :func:`test_the_join_is_greppable_in_both_directions` is the
assertion that this is no longer so, and it asserts on the real file bytes.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial
from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
    LEVEL4_EVENT_TYPES,
    LEVEL4_OBJECT_TYPES,
    build_level4_ocel,
    link_commitment_ttl,
    read_commitment,
)
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.refusals import OcelError

_CONFORMANCE = pathlib.Path(__file__).parents[1] / "ocel" / "test_ocel2_conformance.py"


def _ocel20_schema() -> dict:
    """The real published draft-07 schema, read from the module that owns it."""
    spec = importlib.util.spec_from_file_location("_ocel2_conformance", _CONFORMANCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.OCEL20_JSON_SCHEMA


@pytest.fixture(scope="module")
def executed_trial(tmp_path_factory) -> pathlib.Path:
    """One real Level 4 trial: real probing, real planner federation, real
    gymact actuation subprocess, real receipts. Module-scoped because it is a
    genuine multi-second end-to-end run, not because it is being shared to
    hide state -- every test below reads it, none mutates it except the two
    that own the commitment link, and those are ordered by dependency.
    """
    root = tmp_path_factory.mktemp("level4_ocel")
    report = run_real_trial(
        3979297810, "resource_flow", {"target": 3, "capacity": 4, "mine_rate": 1}, root
    )
    if report.outcome != "EXECUTED":
        pytest.skip(
            f"UNSUPPORTED: trial did not reach actuation (outcome={report.outcome}); "
            "this suite tests the executed chain, and a non-executed trial is a "
            "different (also legitimate) case covered by "
            "test_a_trial_without_a_ledger_reports_absence_not_emptiness"
        )
    return pathlib.Path(report.evidence_dir)


@pytest.fixture(scope="module")
def linked_trial(executed_trial: pathlib.Path) -> pathlib.Path:
    """The same trial after the commitment has been bound to the episode."""
    built = build_level4_ocel(executed_trial)
    assert built.episode_id is not None and built.environment_id is not None
    link_commitment_ttl(
        executed_trial / "actuation" / "commitment.ttl",
        episode_id=built.episode_id,
        environment_id=built.environment_id,
    )
    rebuilt = build_level4_ocel(executed_trial)
    (executed_trial / "actuation" / "level4.ocel.json").write_text(
        json.dumps(rebuilt.log.to_ocel2_json(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return executed_trial


# ── the vocabulary is actually populated from real data ──────────────────


def test_every_chain_event_and_object_type_is_backed_by_real_data(linked_trial) -> None:
    built = build_level4_ocel(linked_trial)
    report = built.report

    # Populated + absent must partition the declared vocabulary. A term that
    # is in neither would be a silently dropped one.
    assert set(report.populated_object_types) | {n for n, _ in report.absent_object_types} == set(
        LEVEL4_OBJECT_TYPES
    )
    assert set(report.populated_event_types) | {n for n, _ in report.absent_event_types} == set(
        LEVEL4_EVENT_TYPES
    )

    assert report.populated_object_types == LEVEL4_OBJECT_TYPES, (
        f"absent object types: {report.absent_object_types}"
    )
    assert report.populated_event_types == LEVEL4_EVENT_TYPES, (
        f"absent event types: {report.absent_event_types}"
    )

    # Every declared object type actually has at least one instance, and every
    # declared event type at least one occurrence -- a name in the report with
    # no member behind it would be the report lying.
    present_object_types = {o.object_type for o in built.log.objects}
    present_activities = {e.activity for e in built.log.events}
    assert present_object_types == set(LEVEL4_OBJECT_TYPES)
    assert present_activities == set(LEVEL4_EVENT_TYPES)


def test_authority_envelope_carries_the_ref_and_omits_the_absent_evidence_ref(
    linked_trial,
) -> None:
    """``authority_ref`` is populated in the real ledger; ``authority_evidence_ref``
    is not. The envelope must carry the first and simply not carry the second --
    an attribute rendered as null would be indistinguishable from an observed null.
    """
    rows = _receipts(linked_trial)
    with_ref = [r for r in rows if r.get("authority_ref")]
    with_evidence = [r for r in rows if r.get("authority_evidence_ref")]
    assert with_ref, "ledger carries no authority_ref at all; the premise of this test is gone"

    built = build_level4_ocel(linked_trial)
    envelopes = [o for o in built.log.objects if o.object_type == "AuthorityEnvelope"]
    assert envelopes
    keys = {a.key for env in envelopes for a in env.attributes}
    assert "authority_ref" in keys
    if not with_evidence:
        assert "authority_evidence_ref" not in keys, (
            "no receipt carries authority_evidence_ref, so the envelope must not "
            "claim one"
        )


# ── the join: the whole point ────────────────────────────────────────────


def test_the_join_is_greppable_in_both_directions(linked_trial) -> None:
    """The measured defect, closed and asserted on real bytes.

    Before: plan digest in the OCEL -> 0 hits; episode id in the TTL -> 0 hits.
    """
    actuation = linked_trial / "actuation"
    commitment = read_commitment(actuation / "commitment.ttl")
    ttl_text = (actuation / "commitment.ttl").read_text(encoding="utf-8")
    ocel_text = (actuation / "level4.ocel.json").read_text(encoding="utf-8")

    built = build_level4_ocel(linked_trial)
    episode_id = built.episode_id
    assert episode_id

    # direction 1: the committed plan digest is findable inside the event log
    assert ocel_text.count(commitment.plan_digest) > 0
    assert ocel_text.count(commitment.model_digest) > 0
    # direction 2: the observed episode is findable inside the commitment
    assert ttl_text.count(episode_id) > 0
    assert ttl_text.count(built.environment_id or "\0") > 0
    # and the commitment re-parses to the same identity it was given
    assert commitment.episode_id == episode_id
    assert commitment.environment_id == built.environment_id


def test_rebinding_a_commitment_to_a_different_episode_is_refused(linked_trial) -> None:
    path = linked_trial / "actuation" / "commitment.ttl"
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="COMMITMENT_ALREADY_BOUND"):
        link_commitment_ttl(path, episode_id="a-different-episode", environment_id="urn:other")
    assert path.read_text(encoding="utf-8") == before, "a refused rebind must not write"


def test_committed_sequence_and_actuated_capabilities_are_now_comparable(linked_trial) -> None:
    """The conformance question itself, answered from the log alone.

    This is the payoff: with the join in place, the committed action sequence
    and the capabilities the receipts say were actually exercised can be
    compared without consulting the filesystem layout.
    """
    built = build_level4_ocel(linked_trial)
    assert built.commitment is not None
    committed = built.commitment.sequence
    assert committed, "commitment carries no sequence"

    by_id = {o.id: o for o in built.log.objects}
    actuated: list[str] = []
    for event in built.log.events:
        if event.activity != "ActuationOpened":
            continue
        for link in built.log.event_object_links:
            if link.event_id == event.id and by_id[link.object_id].object_type == "Capability":
                actuated.append(link.object_id)

    # Every committed action name appears in some exercised capability ref.
    # (Capability refs are namespaced URNs ending in the action name.)
    for action in committed:
        assert any(cap.endswith(action) for cap in actuated), (
            f"committed action {action!r} has no exercised capability among {actuated}"
        )


# ── the relationships gymact's exporter drops ────────────────────────────


def test_o2o_edges_absent_from_the_gymact_export_are_present_here(linked_trial) -> None:
    built = build_level4_ocel(linked_trial)
    qualifiers = {link.qualifier for link in built.log.object_object_links}
    for required in (
        "actuates_commitment",  # committed plan <-> what actually ran
        "caused_by",  # parent_receipt_ids: the causal DAG
        "authorized_by",  # actuation <-> authority envelope
        "observes_actuation",  # postcondition <-> the actuation it observed
    ):
        assert required in qualifiers, f"missing O2O qualifier {required!r}"

    # The causal DAG must have exactly as many edges as the ledger has
    # parent references, so none is dropped and none invented.
    rows = _receipts(linked_trial)
    ids = {r["receipt_id"] for r in rows}
    expected = sum(1 for r in rows for p in (r.get("parent_receipt_ids") or []) if p in ids)
    assert expected > 0, "ledger records no parent_receipt_ids; premise gone"
    actual = sum(1 for link in built.log.object_object_links if link.qualifier == "caused_by")
    assert actual == expected

    # The old gymact export, on the same trial, has no O2O table at all.
    legacy = json.loads((linked_trial / "actuation" / "episode.ocel.json").read_text())
    assert not any(o.get("relationships") for o in legacy["objects"]), (
        "premise changed: the gymact export now carries object relationships"
    )


# ── validation with the real machinery ───────────────────────────────────


def test_log_passes_the_real_ocel_validators(linked_trial) -> None:
    log = build_level4_ocel(linked_trial).log
    assert log.validate(strict_qualifiers=True) is log
    # Task is the reference object: Gianola Assumption 3 requires exactly one
    # per event, which is only true because every event links the Task.
    assert log.validate_locality("Task", "Receipt") is log
    assert log.validate_locality("Task", "Actuation") is log


def test_roundtrip_through_ocel2_json_is_digest_stable(linked_trial) -> None:
    log = build_level4_ocel(linked_trial).log
    document = log.to_ocel2_json()
    restored = OcelLog.from_ocel2_json(document)
    assert restored.digest() == log.digest()
    assert restored.to_ocel2_json() == document

    # The digest is a function of the data, not of build order.
    again = build_level4_ocel(linked_trial).log
    assert again.digest() == log.digest()


def test_emitted_document_validates_against_the_published_ocel2_schema(linked_trial) -> None:
    jsonschema = pytest.importorskip(
        "jsonschema", reason="UNSUPPORTED: jsonschema not installed"
    )
    document = build_level4_ocel(linked_trial).log.to_ocel2_json()
    validator = jsonschema.Draft7Validator(_ocel20_schema())
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))

    # The package deliberately emits *native* typed values (spec section 8:
    # "Valid types are string, time, integer, float, and boolean"), which the
    # literal draft-07 schema -- which types every ``value`` as ``string`` --
    # rejects. That divergence is owned and pinned by
    # ``tests/ocel/test_ocel2_conformance.py::
    # test_native_typed_values_fail_the_published_schema_but_match_the_spec_text``.
    # This log carries integers and booleans, so it inherits exactly that
    # divergence and nothing else. Asserting "no errors" here would require
    # stringifying real typed attributes, i.e. weakening the data to please a
    # test; asserting "only this error class" is the honest, and strictly
    # stronger-than-nothing, check -- any structural schema error still fails.
    unexpected = [e for e in errors if not e.message.endswith("is not of type 'string'")]
    assert not unexpected, "\n".join(f"{list(e.path)}: {e.message}" for e in unexpected[:10])

    # Every remaining error must sit on an attribute value whose declared type
    # is a non-string OCEL type -- not on an id, activity, timestamp or
    # qualifier, all of which really are strings and must validate cleanly.
    declared: dict[tuple[str, str], str] = {}
    for section, key in (("eventTypes", "events"), ("objectTypes", "objects")):
        for type_declaration in document[section]:
            for attribute in type_declaration["attributes"]:
                declared[(key, attribute["name"])] = attribute["type"]
    for error in errors:
        path = list(error.path)
        assert len(path) == 5 and path[2] == "attributes" and path[4] == "value", (
            f"schema error outside an attribute value: {path}: {error.message}"
        )
        name = document[path[0]][path[1]]["attributes"][path[3]]["name"]
        assert declared[(path[0], name)] in {"integer", "float", "boolean"}, (
            f"attribute {name!r} is declared {declared[(path[0], name)]!r} yet is not a string"
        )


def test_the_file_written_to_disk_is_the_document_that_validates(linked_trial) -> None:
    """The emitted bytes, not an in-memory object, are what a reader gets."""
    on_disk = json.loads(
        (linked_trial / "actuation" / "level4.ocel.json").read_text(encoding="utf-8")
    )
    restored = OcelLog.from_ocel2_json(on_disk)
    assert restored.validate(strict_qualifiers=True) is restored
    assert restored.digest() == build_level4_ocel(linked_trial).log.digest()


# ── absence is not evidence ──────────────────────────────────────────────


def test_a_trial_without_a_ledger_reports_absence_not_emptiness(tmp_path) -> None:
    """A directory with probes but no actuation must yield named absences.

    The failure this guards is the one the repo rule names: reporting an empty
    Actuation set as "no actuations occurred" when the truth is "no ledger was
    found, so it is UNKNOWN whether any did".
    """
    trial = tmp_path / "realtrial_7_deadbeef-0000-0000-0000-000000000000"
    trial.mkdir()
    (trial / "typed_probe_log.json").write_text(
        json.dumps({"probe_log": [{"action": "mine", "applicable": True}]}), encoding="utf-8"
    )

    built = build_level4_ocel(trial)
    report = built.report
    assert "Task" in report.populated_object_types
    assert "Probe" in report.populated_object_types

    absent = {name: reason for name, reason in report.absent_object_types}
    for name in ("Receipt", "Actuation", "Replay", "POWLCommitment", "AuthorityEnvelope"):
        assert name in absent, f"{name} silently omitted rather than reported absent"
        assert absent[name], f"{name} absent with no reason given"

    missing_sources = {name for name, _ in report.sources_absent}
    assert "actuation/receipts.sqlite3" in missing_sources
    assert "actuation/commitment.ttl" in missing_sources

    # Still a structurally valid OCEL log, just a smaller one.
    assert built.log.validate(strict_qualifiers=True) is built.log
    assert built.log.validate_locality("Task", "Probe") is built.log


def test_a_dangling_reference_is_still_refused(linked_trial) -> None:
    """The validators are load-bearing here, not decorative."""
    from dataclasses import replace

    from autofde_lab.ocel.model import ObjectObjectLink

    log = build_level4_ocel(linked_trial).log
    broken = replace(
        log,
        object_object_links=log.object_object_links
        + (ObjectObjectLink(log.objects[0].id, "urn:not:declared", "invented"),),
    )
    with pytest.raises(OcelError):
        broken.validate()


# ── helper ────────────────────────────────────────────────────────────────


def _receipts(trial: pathlib.Path) -> list[dict]:
    ledger = trial / "actuation" / "receipts.sqlite3"
    conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        return [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT receipt_json FROM receipt_evidence ORDER BY sequence"
            )
        ]
    finally:
        conn.close()
