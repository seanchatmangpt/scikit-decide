# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `autofde_lab.powl.conformance`: real token-replay
conformance of the real POWL 2.0 diagnosis-pipeline model against a real
OCEL 2.0 event log.

Real collaborators throughout, zero mocks:

- The real production model (`build_pipeline_powl_node()`), not a toy.
- A real `OcelLog` produced by the real `replay_structural_fires` driver --
  the real INTENDED (POWL) -> real produced OBSERVED (OCEL) direction --
  then checked in the OTHER direction (OBSERVED -> conforms-to-INTENDED?)
  by `check_ocel_conformance`, an independent function reading only the
  log's own real events, never the `Marking` `replay_structural_fires`
  produced internally.
- Real, deliberate mutations of that real log (dropping a real event,
  swapping two really-ordered real events) as adversarial negative
  controls -- proving the checker actually discriminates, not merely
  returns `True` unconditionally.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from autofde_lab.ocel.powl_replay import replay_structural_fires
from autofde_lab.powl.conformance import check_ocel_conformance, observed_labels_from_events
from autofde_lab.powl.runner import build_pipeline_powl_node


def test_a_real_log_the_model_itself_produced_conforms_to_itself():
    """Positive control: `replay_structural_fires` drives the real model
    forward and records a real OCEL log of what it actually did -- that
    log must conform to the same model, checked by an independent
    function that never touches `replay_structural_fires`'s own internal
    `Marking`."""
    node = build_pipeline_powl_node()
    log = replay_structural_fires(node, session_id="conformance-positive-control")

    observed = observed_labels_from_events(log.events)
    assert len(observed) == len(log.events) == 22, (
        "every one of the 22 real structural fires from "
        "test_replay_structural_fires_invokes_real_action_bindings_one_event_per_fire "
        "must be readable back off the log's own real `detail` attributes"
    )

    result = check_ocel_conformance(node, log.events)
    assert result.conforms is True
    assert result.final is True
    assert result.fired_count == result.observed_count == 22
    assert result.divergence_index is None
    assert result.divergence_label is None


def test_dropping_a_real_event_is_a_real_detected_divergence():
    """Adversarial negative control: delete the real `case_hit` event from
    an otherwise-real, otherwise-conforming log. `cbr_retain` -- the very
    next real observed event -- only becomes enabled once `case_hit` (or
    `case_miss`) has actually fired, so replay must diverge exactly there,
    naming `cbr_retain` as the label with no matching enabled path."""
    node = build_pipeline_powl_node()
    log = replay_structural_fires(node, session_id="conformance-dropped-event")

    labels = observed_labels_from_events(log.events)
    case_hit_index = labels.index("case_hit")
    mutated_events = tuple(
        event for i, event in enumerate(log.events) if i != case_hit_index
    )
    mutated_labels = observed_labels_from_events(mutated_events)
    assert "case_hit" not in mutated_labels
    assert mutated_labels[case_hit_index] == "cbr_retain", (
        "the mutation must really remove exactly the case_hit event, "
        "leaving cbr_retain as the very next observed label"
    )

    result = check_ocel_conformance(node, mutated_events)
    assert result.conforms is False
    assert result.divergence_index == case_hit_index
    assert result.divergence_label == "cbr_retain"
    assert "cbr_retain" not in (result.divergence_enabled_labels or ())
    # Everything real BEFORE the drop still replayed fine.
    assert result.fired_count == case_hit_index


def test_swapping_two_really_ordered_events_is_a_real_detected_divergence():
    """A second, structurally different adversarial control: `scan` and
    `phi_encode` are real, linearly-ordered siblings (`scan -> phi_encode`)
    in the top-level linear prefix -- not concurrent. Swapping their real
    log order must diverge at the swapped `scan` position, since
    `phi_encode` is not yet enabled before `scan` has fired."""
    node = build_pipeline_powl_node()
    log = replay_structural_fires(node, session_id="conformance-swapped-events")

    labels = observed_labels_from_events(log.events)
    scan_index = labels.index("scan")
    phi_index = labels.index("phi_encode")
    assert phi_index == scan_index + 1, "scan and phi_encode must be adjacent in the real log"

    events = list(log.events)
    events[scan_index], events[phi_index] = events[phi_index], events[scan_index]
    mutated_events = tuple(events)
    mutated_labels = observed_labels_from_events(mutated_events)
    assert mutated_labels[scan_index] == "phi_encode"

    result = check_ocel_conformance(node, mutated_events)
    assert result.conforms is False
    assert result.divergence_index == scan_index
    assert result.divergence_label == "phi_encode"
    assert result.fired_count == scan_index
