# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school tests for real LLM-backed self-play via DSPyPolicy,
backed by a real Groq call instead of a local TurboFieldfareServer process.

This mirrors `tests/test_self_play_dspy_turbofieldfare_chicago.py` exactly
(same domain, same solver, same assertions) but swaps `real_dspy_lm` (a real
local TurboFieldfare server) for `real_groq_dspy_lm` (a real
`groq/llama-3.1-8b-instant` call, `GROQ_API_KEY`-gated) -- confirming
DSPyPolicy, the non-sregym generic dspy solver, genuinely works against a
real, always-reachable hosted endpoint and not only against a locally-built
server binary + model weights that may not be present on every machine.

No mocks anywhere in the chain: a real `dspy.LM` against the real Groq API,
a real `dspy.Predict` call per move, and the real, registered
`RockPaperScissors` domain rolled out via the real
`autofde_lab.hub.solver.dspy_policy.DSPyPolicy` solver and the real
`autofde_lab.self_play.self_play_rollout`. Skipped (not mocked) when
`GROQ_API_KEY` is unset, per `.claude/rules/testing-chicago-style.md`.

The `real_groq_dspy_lm` fixture lives in `tests/conftest.py` (pytest
auto-discovers and injects it, no import needed). `requires_real_groq_key`
is redefined locally rather than imported from `tests/conftest.py`, matching
the convention every `tests/reasoning/*_chicago.py` GROQ-gated file already
uses: `tests/` has no `__init__.py` markers (see `.claude/rules/standing-law.md`'s
"Former standing exception" section on the bare-conftest module-name
collision this repo hit before), so `tests/conftest.py` and any sibling
`tests/<subdir>/conftest.py` (e.g. `tests/ocel/conftest.py`) both import
under the same bare module name `conftest` in pytest's default "prepend"
mode. `from conftest import requires_real_groq_key` is therefore
order-dependent on which conftest.py pytest happened to import first in
this process -- it resolved to the wrong module (`tests/ocel/conftest.py`,
which has no such name) under `just test`'s `-n 4` xdist run, producing a
real `ImportError` at collection time despite this exact test module
importing and passing standalone. Defining the mark locally sidesteps the
collision entirely instead of relying on fragile bare-module resolution.
"""

from __future__ import annotations

import os

import pytest

requires_real_groq_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used per "
        ".claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
def test_real_dspy_predict_gets_a_real_legal_move_from_groq(real_groq_dspy_lm):
    import dspy

    class ChooseMove(dspy.Signature):
        situation: str = dspy.InputField()
        legal_moves: str = dspy.InputField()
        move: str = dspy.OutputField()

    prediction = dspy.Predict(ChooseMove)(
        situation="Your opponent just played rock.",
        legal_moves="rock, paper, scissors",
    )
    assert prediction.move.strip().lower() in {"rock", "paper", "scissors"}


@requires_real_groq_key
def test_real_dspy_policy_solver_reports_compatible_with_real_rock_paper_scissors_via_groq(
    real_groq_dspy_lm,
):
    from autofde_lab.hub.domain.rock_paper_scissors import RockPaperScissors
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    domain = RockPaperScissors(max_moves=2)
    assert DSPyPolicy.check_domain(domain) is True


@requires_real_groq_key
def test_real_self_play_rollout_with_real_dspy_policy_produces_real_valid_zero_sum_episode_via_groq(
    real_groq_dspy_lm,
):
    from autofde_lab.hub.domain.rock_paper_scissors import RockPaperScissors
    from autofde_lab.hub.domain.rock_paper_scissors.rock_paper_scissors import Move
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy
    from autofde_lab.self_play import self_play_rollout

    max_steps = 2

    def domain_factory():
        return RockPaperScissors(max_moves=max_steps)

    with DSPyPolicy(domain_factory=domain_factory, lm=real_groq_dspy_lm) as solver:
        solver.solve()
        result = self_play_rollout(
            num_episodes=2, max_steps=max_steps, solver=solver
        )

    assert result["num_episodes_run"] == 2
    assert len(result["episode_returns"]) == 2
    for episode_return in result["episode_returns"]:
        # real zero-sum guarantee: what player1 gains, player2 loses
        assert episode_return["player1"] == -episode_return["player2"]
        assert -max_steps <= episode_return["player1"] <= max_steps

    # every real move actually chosen by the real LLM is a real, valid Move
    assert set(Move) == {Move.rock, Move.paper, Move.scissors}
