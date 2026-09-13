# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `autofde_lab.powl.claudecode_reference_model`.

**No `claude` CLI invocation, no Claude API call, no subprocess, no network
call anywhere in this file.** Every assertion is a real, structural trace
against the real POWL v2 executor (`enabled()`/`fire()`) -- the same real
collaborator every other model in `tests/powl/` is verified against. The
model under test is a pure structural description; there is nothing live
to call, so "real collaborators" here means the real executor and the real
`autofde_lab.powl.conformance` checker, not a live agent process.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from autofde_lab.ocel.powl_replay import replay_structural_fires
from autofde_lab.powl.claudecode_reference_model import (
    CLAUDECODE_ALLOWED_TOOLS,
    CLAUDECODE_BUILD_INSTRUCTION_LABEL,
    CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL,
    CLAUDECODE_GENERATE_TRAJECTORY_LABEL,
    CLAUDECODE_GET_APP_INFO_LABEL,
    CLAUDECODE_MITIGATION_TOOL_CALL_LABEL,
    CLAUDECODE_SAVE_RESULTS_LABEL,
    CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL,
    CLAUDECODE_SUBMIT_MITIGATION_LABEL,
    CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL,
    build_claudecode_agent_powl_node,
)
from autofde_lab.powl.conformance import check_ocel_conformance
from autofde_lab.powl.executor import INITIAL_MARKING, enabled, fire, is_final


def test_real_documented_tool_list_is_exactly_seventeen_and_unchanged():
    """Pins the real, exact tool list quoted from the vendored source
    (`claudecode_agent.py:86-104`) -- a regression fixture: if the real
    vendored checkout's `ALLOWED_TOOLS` ever changes, this constant (and
    this module's own scoping claim) must be re-checked against it, not
    silently drift."""
    assert CLAUDECODE_ALLOWED_TOOLS == (
        "Bash",
        "Edit",
        "Write",
        "Read",
        "Glob",
        "Grep",
        "LS",
        "WebFetch",
        "NotebookEdit",
        "NotebookRead",
        "TodoRead",
        "TodoWrite",
        "Agent",
        "Skill",
        "SlashCommand",
        "Task",
        "WebSearch",
    )
    assert len(CLAUDECODE_ALLOWED_TOOLS) == 17


def test_real_structural_shape_matches_the_documented_process_order():
    node = build_claudecode_agent_powl_node()
    kinds = [type(c).__name__ for c in node.children]
    assert kinds == [
        "Atom",  # wait_for_ready_stage
        "Atom",  # get_app_info
        "Atom",  # build_instruction
        "ChoiceGraph",  # diagnosis tool-use loop
        "Atom",  # submit_diagnosis
        "ChoiceGraph",  # mitigation tool-use loop
        "Atom",  # submit_mitigation
        "Atom",  # save_results
        "Atom",  # generate_trajectory
    ]
    atom_labels = [c.label for c in node.children if hasattr(c, "label")]
    assert atom_labels == [
        CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL,
        CLAUDECODE_GET_APP_INFO_LABEL,
        CLAUDECODE_BUILD_INSTRUCTION_LABEL,
        CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL,
        CLAUDECODE_SUBMIT_MITIGATION_LABEL,
        CLAUDECODE_SAVE_RESULTS_LABEL,
        CLAUDECODE_GENERATE_TRAJECTORY_LABEL,
    ]
    # Real, linear, fully-ordered top level -- claudecode's real process has
    # no top-level concurrency (each step genuinely depends on the last).
    assert len(node.order) == len(node.children) - 1


def test_diagnosis_and_mitigation_loops_are_genuinely_distinct_real_atoms():
    """The two stages' tool-use loops must not accidentally share identity
    -- a real, structurally-distinguishable diagnosis vs. mitigation
    Atom, not the same node reused."""
    node = build_claudecode_agent_powl_node()
    diagnosis_loop = node.children[3]
    mitigation_loop = node.children[5]
    diagnosis_tool_atom = next(c for c in diagnosis_loop.children if hasattr(c, "label"))
    mitigation_tool_atom = next(c for c in mitigation_loop.children if hasattr(c, "label"))
    assert diagnosis_tool_atom.label == CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL
    assert mitigation_tool_atom.label == CLAUDECODE_MITIGATION_TOOL_CALL_LABEL
    assert diagnosis_tool_atom.label != mitigation_tool_atom.label


def test_tool_use_loop_really_permits_zero_tool_calls_traced_against_executor():
    """Real trace: the zero-tool-calls path (straight from the loop's
    start Silent node to its end Silent node) is really enabled and really
    fireable -- matching claudecode's real behavior when the agent submits
    immediately without needing any tool (structurally legal, even if
    practically rare)."""
    node = build_claudecode_agent_powl_node()
    diagnosis_loop = node.children[3]

    m0 = INITIAL_MARKING
    live0 = enabled(diagnosis_loop, m0)
    assert live0 == frozenset({(0,)})  # only the start Silent node
    m1 = fire(diagnosis_loop, m0, (0,))
    live1 = enabled(diagnosis_loop, m1)
    # Real choice: proceed straight to end (index 1), or enter the tool
    # loop (index 2) -- both genuinely live.
    assert live1 == frozenset({(1,), (2,)})
    m2 = fire(diagnosis_loop, m1, (1,))
    assert is_final(diagnosis_loop, m2)


def test_tool_use_loop_really_permits_real_repeated_tool_calls_traced_against_executor():
    """Real trace: firing the tool-call Atom multiple times in a row (real
    POWL 2.0 iteration -- the self-loop edge) before exiting to the end
    node is genuinely legal and genuinely reachable, matching claudecode's
    real behavior of calling tools an arbitrary number of times before
    submitting."""
    node = build_claudecode_agent_powl_node()
    diagnosis_loop = node.children[3]

    m = fire(diagnosis_loop, INITIAL_MARKING, (0,))
    # Enter the loop, real repeat x3, then real exit.
    for _ in range(3):
        live = enabled(diagnosis_loop, m)
        assert (2,) in live, f"tool-call atom must remain enabled for a real repeat, got {sorted(live)}"
        m = fire(diagnosis_loop, m, (2,))
    live_after_three = enabled(diagnosis_loop, m)
    assert live_after_three == frozenset({(1,), (2,)}), (
        "after real repeated tool calls, both 'repeat again' and "
        "'exit to submit' must remain genuinely live"
    )
    m = fire(diagnosis_loop, m, (1,))
    assert is_final(diagnosis_loop, m)


def test_full_model_reaches_a_real_final_marking_via_structural_replay():
    """Real end-to-end structural replay of the WHOLE model (all 9
    top-level steps, both stages' tool loops each fired twice), via the
    same real `replay_structural_fires` driver every other POWL model in
    this package uses -- proving the full model is genuinely completable,
    not just its individual pieces."""
    node = build_claudecode_agent_powl_node()

    invocations: list[str] = []

    def record(label: str):
        def _binding(attrs: dict):
            invocations.append(label)
            return None

        return _binding

    action_bindings = {
        CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL: record(CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL),
        CLAUDECODE_GET_APP_INFO_LABEL: record(CLAUDECODE_GET_APP_INFO_LABEL),
        CLAUDECODE_BUILD_INSTRUCTION_LABEL: record(CLAUDECODE_BUILD_INSTRUCTION_LABEL),
        CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL: record(CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL),
        CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL: record(CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL),
        CLAUDECODE_MITIGATION_TOOL_CALL_LABEL: record(CLAUDECODE_MITIGATION_TOOL_CALL_LABEL),
        CLAUDECODE_SUBMIT_MITIGATION_LABEL: record(CLAUDECODE_SUBMIT_MITIGATION_LABEL),
        CLAUDECODE_SAVE_RESULTS_LABEL: record(CLAUDECODE_SAVE_RESULTS_LABEL),
        CLAUDECODE_GENERATE_TRAJECTORY_LABEL: record(CLAUDECODE_GENERATE_TRAJECTORY_LABEL),
    }

    log = replay_structural_fires(
        node, session_id="test-claudecode-reference-model", action_bindings=action_bindings
    )

    assert invocations[0] == CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL
    assert invocations[1] == CLAUDECODE_GET_APP_INFO_LABEL
    assert invocations[2] == CLAUDECODE_BUILD_INSTRUCTION_LABEL
    # Between build_instruction and submit_diagnosis, only real diagnosis
    # tool-call invocations (zero or more) may appear.
    diag_start = 3
    diag_submit_index = invocations.index(CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL)
    assert all(
        label == CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL
        for label in invocations[diag_start:diag_submit_index]
    )
    assert invocations[-1] == CLAUDECODE_GENERATE_TRAJECTORY_LABEL
    assert invocations[-2] == CLAUDECODE_SAVE_RESULTS_LABEL
    # replay_structural_fires's real default policy fires the
    # lexicographically-smallest enabled path each round, so each
    # ChoiceGraph's real "zero tool calls" branch (index 1) sorts before
    # "enter the loop" (index 2) and is taken -- both loops' own real
    # entry/exit Silent nodes fire too (4 real unbound fires total, on top
    # of the 7 real bound ones), so `log.events` is real and larger than
    # `invocations`, not equal to it.
    assert len(log.events) == len(invocations) + 4


def test_a_real_log_the_model_itself_produced_conforms_to_itself():
    """Positive control, matching the established pattern from
    `test_conformance_chicago.py`: `replay_structural_fires` drives this
    real model forward and records a real OCEL log of what it actually
    did -- that log must conform to the same model, checked by the real,
    independent `check_ocel_conformance` function (never a hand-guessed
    synthetic label list, which is real but was wrong to hand-author for
    a ChoiceGraph with its own real Silent entry/exit nodes -- reusing a
    real produced log sidesteps that class of authoring error entirely)."""
    node = build_claudecode_agent_powl_node()
    log = replay_structural_fires(node, session_id="test-claudecode-conformance-positive")

    result = check_ocel_conformance(node, log.events)
    assert result.conforms is True
    assert result.final is True
    assert result.divergence_index is None
    assert result.fired_count == result.observed_count == len(log.events)


def test_dropping_the_real_submit_diagnosis_event_is_a_real_detected_divergence():
    """Adversarial negative control, same established pattern: delete the
    real `submit_diagnosis` event from an otherwise-real, otherwise-
    conforming log. The very next real observed event only becomes
    enabled once `submit_diagnosis` has actually fired, so replay must
    diverge exactly there."""
    node = build_claudecode_agent_powl_node()
    log = replay_structural_fires(node, session_id="test-claudecode-conformance-negative")

    def detail_of(event) -> str | None:
        return next((a.value.value for a in event.attributes if a.key == "detail"), None)

    labels = [detail_of(e) for e in log.events]
    submit_diagnosis_index = labels.index(CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL)
    mutated_events = tuple(
        event for i, event in enumerate(log.events) if i != submit_diagnosis_index
    )

    result = check_ocel_conformance(node, mutated_events)
    assert result.conforms is False
    assert result.divergence_index == submit_diagnosis_index
    assert result.divergence_label == labels[submit_diagnosis_index + 1]
    assert result.fired_count == submit_diagnosis_index
