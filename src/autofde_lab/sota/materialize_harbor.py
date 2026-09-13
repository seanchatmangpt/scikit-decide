# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The real, current DecisionBasis point for `harbor`'s `terminus-2` agent, and the real
invocation it materializes to. Grounded against the real, already-executed
`hello-world__Q7JV4qH` trial this session ran (reward 1.0, 4 real episodes) -- every field
below is cited against `vendor/gyms/harbor/src/harbor/agents/terminus_2/terminus_2.py` and
cross-checked against that trial's own real `result.json`/`trajectory.json`, not merely the
source in isolation.

Unlike `materialize_sregym.py`'s D0 (whose tool/repair/step fields live in a real, separately
mutable vendor YAML), terminus-2's tool/repair/budget shape is not driven by an external
config file the caller edits per-run -- it is largely constructor/class-level defaults in
`terminus_2.py` itself, plus the task's own `task.toml`. `current_harbor_terminus2_basis()`
therefore cites the real source constants directly (each with its exact file:line), rather
than reading a file at call time -- there is no separate vendor config file to read without
duplicating; the source *is* the config here, and this function is the typed transcription of
it, not a second copy of a fact recorded elsewhere.
"""

from __future__ import annotations

from pathlib import Path

from autofde_lab.sota.decision_basis import (
    Budget,
    DecisionBasis,
    Model,
    Planner,
    RepairPolicy,
    ToolPolicy,
    VerificationPolicy,
)

HARBOR_ROOT = Path(__file__).resolve().parents[3] / "vendor" / "gyms" / "harbor"

#: Real path to the hello-world task's own agent-timeout declaration -- cited:
#: vendor/gyms/harbor/examples/tasks/hello-world/task.toml:19-20 ([agent] timeout_sec = 120.0).
HELLO_WORLD_TASK_PATH = HARBOR_ROOT / "examples" / "tasks" / "hello-world"

#: Real, final grading path for any harbor task -- cited:
#: vendor/gyms/harbor/src/harbor/verifier/verifier.py:138-238 (`Verifier.verify()`), a plain
#: shell exec of the task's own `tests/` script, strictly after and independent of the agent
#: phase (`vendor/gyms/harbor/src/harbor/trial/single_step.py:38-56`). For hello-world this is
#: `tests/test.sh` running `pytest tests/test_state.py`, confirmed live this session
#: (reward 1.0).
HARBOR_VERIFIER_ORACLE = "harbor.Verifier (task-bundled tests/ script, e.g. tests/test.sh)"


def current_harbor_terminus2_basis(
    *,
    model_id: str = "hosted_vllm/gemma-4-26b-a4b-it",
    api_base: str = "http://127.0.0.1:8080/v1",
    api_key_placeholder: str | None = None,
    task_path: str = "examples/tasks/hello-world",
    agent_timeout_s: float = 120.0,
) -> DecisionBasis:
    """The real DecisionBasis point this session's real, successful (reward 1.0)
    `harbor`/`terminus-2` run actually exercised.

    ``model_id``/``api_base``/``task_path``/``agent_timeout_s`` default to the exact real
    values that trial used (`--model hosted_vllm/gemma-4-26b-a4b-it --ak
    api_base=http://127.0.0.1:8080/v1 --path examples/tasks/hello-world`, `task.toml`'s
    `timeout_sec = 120.0`) -- overridable because they are real CLI/task-level knobs, not
    hardcoded terminus-2 internals, unlike the tool/repair/budget fields below.
    """
    return DecisionBasis(
        model=Model(
            id=model_id,
            api_base=api_base,
            api_key_placeholder=api_key_placeholder,
            description=(
                "Real local TurboFieldfare/Gemma server via LiteLLM's hosted_vllm provider "
                "(no api_key required -- litellm/llms/hosted_vllm/chat/transformation.py's "
                "own 'vllm does not require an api key' fallback, confirmed this session)."
            ),
        ),
        planner=Planner(
            name="harbor:terminus-2",
            description=(
                "Real iterative loop over one persistent tmux session "
                "(terminus_2.py:_run_agent_loop, :1231-1540): exactly one main-loop LLM call "
                "per episode (n_episodes counts main-loop calls only, NOT context-"
                "summarization calls, which are tracked separately as "
                "summarization_count), terminal output fed back as the next prompt, "
                "double-confirm task_complete gate before the loop returns "
                "(:1408-1415 first true, :1531-1538 second consecutive true). Confirmed "
                "against the real hello-world-v3 trial: 4 episodes = 2 bash_command steps "
                "(write file, verify) + 2 mark_task_complete confirmations."
            ),
        ),
        tool_policy=ToolPolicy(
            tool_names=("bash_command",),
            description=(
                "A SINGLE implicit action -- free-text keystrokes into the shared tmux "
                "terminal, expressed via a JSON-object prompt contract "
                "(templates/terminus-json-plain.txt), parsed by "
                "TerminusJSONPlainParser.parse_response, NOT native LLM tool-calling (no "
                "`tools=[...]` schema passed to the model). terminus_2.py:1430-1433's own "
                "comment: 'Although Terminus 2 doesn't offer native tool calling ..., we "
                "represent parsed commands as tool calls for ... trajectory analysis'. "
                "'bash_command' names the synthesized post-hoc trajectory-logging label, not "
                "a real tool schema entry -- the real action space is exactly one action."
            ),
        ),
        repair_policy=RepairPolicy(
            mode="deterministic-autofix-then-reprompt",
            max_attempts=3,
            description=(
                "Three distinct real layers, no LLM-driven replanning: (1) deterministic "
                "JSON auto-fix for malformed output, zero LLM call "
                "(TerminusJSONPlainParser._get_auto_fixes); (2) on an unrepairable parse "
                "error, a bare re-prompt consumed as the NEXT episode "
                "(terminus_2.py:1355-1397) -- not a dedicated retry subroutine; "
                "(3) tenacity-wrapped 3-attempt retry (stop_after_attempt(3), "
                "terminus_2.py:983-994) around raw LLM-call exceptions only (transport/API "
                "failures), reraised after 3. max_attempts=3 here names layer (3), the only "
                "genuinely bounded/backed-off retry; layers (1)/(2) have no attempt ceiling "
                "of their own beyond the outer episode budget."
            ),
        ),
        verification_policy=VerificationPolicy(
            oracle_name=HARBOR_VERIFIER_ORACLE,
            description=(
                "Real, unmodified, task-bundled verifier -- Verifier.verify() execs the "
                "task's own tests/ script via plain shell exec, zero LLM, zero agent "
                "involvement, strictly after the agent phase completes "
                "(single_step.py:38-56). Confirmed live: agent_execution "
                "05:53:05->05:53:48 (43.6s), verifier 05:53:48->05:54:01 (12.5s, started "
                "only after agent finished), verifier_result.rewards.reward == 1.0."
            ),
        ),
        budget=Budget(
            max_steps=1_000_000,
            max_retry_attempts=3,
            wall_clock_timeout_s=int(agent_timeout_s),
            llm_max_retries=3,
            description=(
                "max_steps=1_000_000 is terminus_2.py:286-302's real hardcoded default "
                "episode cap when no explicit max_turns is passed (task.toml has no "
                "turn-count field at all -- AgentConfig only declares timeout_sec/user, "
                "models/task/config.py:339-343) -- effectively unbounded; the real governing "
                "cap is the wall-clock timeout (task.toml's [agent] timeout_sec, 120.0 for "
                "hello-world, enforced via asyncio.wait_for around the whole agent.run() "
                "call). llm_max_retries=3 is the tenacity stop_after_attempt(3) bound "
                "(terminus_2.py:983-994). Real run finished naturally at episode 4, well "
                "under both the timeout and the episode cap -- neither budget dimension "
                "bound this trial's outcome."
            ),
        ),
        extra={"task_path": task_path},
    )


def materialize_harbor_invocation(basis: DecisionBasis) -> tuple[list[str], dict[str, str]]:
    """The real, exact `harbor run` argv this DecisionBasis point runs as -- the inverse of
    `current_harbor_terminus2_basis()`.

    Only `--model`/`--ak api_base=...`/`--path` are real, independently-settable CLI knobs
    today (`src/harbor/cli/jobs.py:499-545`); the tool/repair/budget fields are terminus-2
    constructor internals with no dedicated CLI surface -- varying them for a real search
    means passing additional `--ak <kwarg>=<value>` pairs matching `Terminus2.__init__`'s real
    parameter names (`max_turns`, `proactive_summarization_threshold`, etc.), which is named
    as future work, not silently pretended to already exist as a flag.

    `model_info` is required by LiteLLM's `hosted_vllm` provider when the model carries no
    built-in cost/limit metadata (`llms/utils.py:101-171`'s real `validate_hosted_vllm_model_
    config`) -- included here unconditionally for any `hosted_vllm/` model id, matching what
    the real run actually needed.
    """
    if basis.planner.name != "harbor:terminus-2":
        raise ValueError(
            f"materialize_harbor_invocation only knows the terminus-2 planner identity; "
            f"got {basis.planner.name!r}"
        )
    argv = [
        "harbor", "run",
        "--agent", "terminus-2",
        "--model", basis.model.id,
        "--path", basis.extra.get("task_path", "examples/tasks/hello-world"),
    ]
    if basis.model.api_base:
        argv += ["--ak", f"api_base={basis.model.api_base}"]
    if basis.model.id.startswith("hosted_vllm/"):
        argv += [
            "--ak",
            'model_info={"max_input_tokens":32768,"max_output_tokens":4096,'
            '"input_cost_per_token":0,"output_cost_per_token":0}',
        ]
    env: dict[str, str] = {"HARBOR_TELEMETRY": "0"}
    return argv, env
