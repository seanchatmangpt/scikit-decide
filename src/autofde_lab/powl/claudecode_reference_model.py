# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real POWL 2.0 structural model of SREGym's real, vendored `claudecode`
agent client -- the literal harness behind the SREGym leaderboard's #1
entry (Claude Code / Claude Sonnet 4.6, no noise: Diagnosis 72.6% /
Mitigation 75.6% / E2E 60.7%, https://sregym.com/leaderboard).

**This module never invokes the real `claude` CLI, the Claude API, or any
network call. No LLM call, no subprocess, no HTTP request happens anywhere
in this module.** It is a pure, real POWL v2 structural DESCRIPTION of that
agent's real, documented process shape, traced directly from the real
vendored source (`vendor/gyms/sregym/clients/claudecode/driver.py` and
`claudecode_agent.py`, read in full this session, quoted precisely below)
-- never invented. It exists so the real shape of the SOTA-holding agent's
workflow can be reasoned about, structurally verified via the same real
executor (`enabled()`/`fire()`) every other model in this package uses, and
eventually checked for real conformance (via `powl.conformance`) against a
real observed trajectory -- without ever running the agent itself.

Real process traced from the vendored source
----------------------------------------------
1. `wait_for_ready_stage()` (`driver.py:84-123`) -- poll the real conductor
   `/status` endpoint until it reaches `"diagnosis"` or `"mitigation"`.
2. `get_app_info()` (`driver.py:68-81`) -- fetch real app metadata
   (`app_name`, `namespace(s)`, `descriptions`) from the conductor.
3. `build_instruction()` (`driver.py:126-192`) -- construct the real task
   prompt text handed to Claude Code.
4. **DIAGNOSIS stage**: a real, LLM-driven, repeatable tool-use loop
   (`ALLOWED_TOOLS` in `claudecode_agent.py:86-104` -- `Bash`, `Edit`,
   `Write`, `Read`, `Glob`, `Grep`, `LS`, `WebFetch`, `NotebookEdit`,
   `NotebookRead`, `TodoRead`, `TodoWrite`, `Agent`, `Skill`,
   `SlashCommand`, `Task`, `WebSearch`), then a submission (`POST /submit`
   with a natural-language solution, per `build_instruction()`'s own
   documented protocol).
5. **MITIGATION stage**: the same real repeatable tool-use loop, then a
   submission (`POST /submit` with an empty string, per the same protocol).
6. `save_results()` (`driver.py:195-224`) / `generate_trajectory()`
   (`claudecode_agent.py:228-279`) -- real post-run artifacts (usage
   metrics extracted from Claude Code's own session JSONL, a converted
   trajectory JSONL for the SREGym visualizer).

Why the tool-use loop is modeled as ONE abstract, self-looping Atom, not
17 individually-distinguished tool Atoms
------------------------------------------------------------------------
POWL 2.0's own iteration construct (a cyclic `ChoiceGraph`, matching this
package's already-established `_self_looping_a()` fixture pattern in
`tests/powl/test_semantics.py`) genuinely captures the real,
structurally-guaranteed shape here: "zero or more tool calls, in whatever
order, before submitting." What it must NOT claim is which of the 17 real
`ALLOWED_TOOLS` gets called, or in what order -- that is real,
LLM-decided nondeterminism, honestly outside the scope of any structural
process model. Modeling all 17 tools as individually-orderable choices
would imply a false level of structural determinism about the agent's
real behavior that this repository has no evidence for and does not
control. The single abstract `*_claudecode_tool_call` Atom per stage is
the honestly-scoped choice: real about the STRUCTURE (iterate, then
submit), silent about the CONTENT (which tool, how many times, what
order) a real trajectory would fill in.
"""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
    Silent,
)

__all__ = [
    "CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL",
    "CLAUDECODE_GET_APP_INFO_LABEL",
    "CLAUDECODE_BUILD_INSTRUCTION_LABEL",
    "CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL",
    "CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL",
    "CLAUDECODE_MITIGATION_TOOL_CALL_LABEL",
    "CLAUDECODE_SUBMIT_MITIGATION_LABEL",
    "CLAUDECODE_SAVE_RESULTS_LABEL",
    "CLAUDECODE_GENERATE_TRAJECTORY_LABEL",
    "CLAUDECODE_ALLOWED_TOOLS",
    "build_claudecode_agent_powl_node",
]

# Real, exact tool list quoted from `claudecode_agent.py:86-104` -- not
# individually modeled as separate Atoms (see module docstring), but kept
# here as a real, checkable record of what the real agent's `--allowedTools`
# flag actually grants, so this module's own scoping claim is verifiable
# against the real vendored source rather than asserted from memory.
CLAUDECODE_ALLOWED_TOOLS: tuple[str, ...] = (
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

CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL = "claudecode_wait_for_ready_stage"
CLAUDECODE_GET_APP_INFO_LABEL = "claudecode_get_app_info"
CLAUDECODE_BUILD_INSTRUCTION_LABEL = "claudecode_build_instruction"
CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL = "claudecode_diagnosis_tool_call"
CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL = "claudecode_submit_diagnosis"
CLAUDECODE_MITIGATION_TOOL_CALL_LABEL = "claudecode_mitigation_tool_call"
CLAUDECODE_SUBMIT_MITIGATION_LABEL = "claudecode_submit_mitigation"
CLAUDECODE_SAVE_RESULTS_LABEL = "claudecode_save_results"
CLAUDECODE_GENERATE_TRAJECTORY_LABEL = "claudecode_generate_trajectory"


def _sequence(nodes: tuple[PowlNode, ...], *, start_index: int) -> frozenset[OrderEdge]:
    """The `OrderEdge` set chaining every adjacent pair in `nodes`, offset
    so `nodes[0]` sits at `start_index`. Local, tiny duplicate of
    `runner.py`'s own private `_sequence()` helper -- not imported from
    there since that symbol is private to that module; this is the same
    real, index-based pattern (matching the real reference `powl`
    package's `builders.py::sequence()`), not a divergent reimplementation."""
    return frozenset(
        OrderEdge(NodeId(start_index + i), NodeId(start_index + i + 1))
        for i in range(len(nodes) - 1)
    )


def _repeatable_tool_use_choice_graph(tool_call_label: str) -> ChoiceGraph:
    """Real POWL v2 model of one stage's real tool-use loop: the agent may
    call an allowed tool zero or more times (real POWL 2.0 iteration, a
    cyclic choice graph -- Section 3.3) before proceeding to submit.

    Shape (matches `tests/powl/test_semantics.py::_self_looping_a()`
    exactly): `start(Silent, 0) -> end(Silent, 1)` directly (zero tool
    calls), OR `start -> tool_call(2) -> tool_call(2)` (self-loop, repeat)
    `-> end`. Real, traceable via `enabled()`/`fire()` like every other
    choice graph in this package -- no invented semantics.
    """
    tool_call = Atom(label=tool_call_label)
    return ChoiceGraph(
        children=(Silent(), Silent(), tool_call),
        edges=frozenset(
            {
                ChoiceGraphEdge(NodeId(0), NodeId(1)),  # zero tool calls -> straight to submit
                ChoiceGraphEdge(NodeId(0), NodeId(2)),  # enter the loop
                ChoiceGraphEdge(NodeId(2), NodeId(2)),  # repeat (self-loop -- real iteration)
                ChoiceGraphEdge(NodeId(2), NodeId(1)),  # exit the loop, proceed to submit
            }
        ),
        start=0,
        end=1,
    )


def build_claudecode_agent_powl_node() -> PowlNode:
    """Real, honest POWL v2 structural model of the real, vendored
    `claudecode` SREGym agent client. See module docstring for the full,
    source-traced process this represents. Returns a `PartialOrder` whose
    children are, in real documented order: the three real setup steps,
    the real diagnosis tool-use-loop + submit, the real mitigation
    tool-use-loop + submit, and the two real post-run artifact steps.
    """
    linear_prefix: tuple[PowlNode, ...] = (
        Atom(label=CLAUDECODE_WAIT_FOR_READY_STAGE_LABEL),
        Atom(label=CLAUDECODE_GET_APP_INFO_LABEL),
        Atom(label=CLAUDECODE_BUILD_INSTRUCTION_LABEL),
    )
    diagnosis_loop = _repeatable_tool_use_choice_graph(CLAUDECODE_DIAGNOSIS_TOOL_CALL_LABEL)
    submit_diagnosis = Atom(label=CLAUDECODE_SUBMIT_DIAGNOSIS_LABEL)
    mitigation_loop = _repeatable_tool_use_choice_graph(CLAUDECODE_MITIGATION_TOOL_CALL_LABEL)
    submit_mitigation = Atom(label=CLAUDECODE_SUBMIT_MITIGATION_LABEL)
    save_results = Atom(label=CLAUDECODE_SAVE_RESULTS_LABEL)
    generate_trajectory = Atom(label=CLAUDECODE_GENERATE_TRAJECTORY_LABEL)

    children: tuple[PowlNode, ...] = linear_prefix + (
        diagnosis_loop,
        submit_diagnosis,
        mitigation_loop,
        submit_mitigation,
        save_results,
        generate_trajectory,
    )
    order = _sequence(children, start_index=0)
    return PartialOrder(children=children, order=order)
