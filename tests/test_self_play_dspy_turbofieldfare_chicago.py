# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school tests for real LLM-backed self-play via DSPyPolicy.

No mocks anywhere in the chain: a real TurboFieldfare server process (local,
OpenAI-compatible, built from https://github.com/drumih/turbo-fieldfare),
a real `dspy.LM` configured against it, a real `dspy.Predict` call per move,
and the real, registered `RockPaperScissors` domain rolled out via the real
`autofde_lab.hub.solver.dspy_policy.DSPyPolicy` solver and the real
`autofde_lab.self_play.self_play_rollout`.

Skipped (not mocked) when the real TurboFieldfareServer binary or model
weights genuinely aren't present on disk, or the real server fails to come
up -- this is a real external dependency this test cannot fake and still be
an end-to-end check of the real integration. When both are present, this
test starts and stops the real server process itself.

The real server-process fixtures (`real_turbo_fieldfare_server`,
`real_dspy_lm`) and the `requires_real_turbo_fieldfare_binary_and_model` skip
marker live in `tests/conftest.py`, shared with
`tests/test_self_play_dspy_all_domains_chicago.py` -- both files exercise the
same real external server, so its lifecycle is implemented exactly once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# `requires_real_turbo_fieldfare_binary_and_model` is redefined locally rather
# than imported from `tests/conftest.py`: `tests/` has no `__init__.py`
# markers (see `.claude/rules/standing-law.md`'s "Former standing exception"
# section on the bare-conftest module-name collision this repo hit before),
# so `tests/conftest.py` and any sibling `tests/<subdir>/conftest.py` both
# import under the same bare module name `conftest` in pytest's default
# "prepend" mode. `from conftest import requires_real_turbo_fieldfare_binary_and_model`
# is therefore order-dependent on which conftest.py pytest happened to import
# first in this process -- exactly the real `ImportError` already found and
# fixed the same way in `tests/test_self_play_dspy_groq_chicago.py`.
_TURBO_FIELDFARE_DIR = Path.home() / "turbo-fieldfare"
_SERVER_BINARY = _TURBO_FIELDFARE_DIR / ".build" / "release" / "TurboFieldfareServer"
_MODEL_PATH = _TURBO_FIELDFARE_DIR / "scratch" / "gemma4.gturbo"

requires_real_turbo_fieldfare_binary_and_model = pytest.mark.skipif(
    not (_SERVER_BINARY.exists() and _MODEL_PATH.exists()),
    reason=(
        f"Real TurboFieldfareServer binary ({_SERVER_BINARY}) or real model "
        f"weights ({_MODEL_PATH}) not present -- build/install them per "
        "turbo-fieldfare's README before running this real end-to-end test."
    ),
)


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_predict_gets_a_real_legal_move_from_the_real_server(real_dspy_lm):
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


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_solver_reports_compatible_with_real_rock_paper_scissors(
    real_dspy_lm,
):
    from autofde_lab.hub.domain.rock_paper_scissors import RockPaperScissors
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    domain = RockPaperScissors(max_moves=2)
    assert DSPyPolicy.check_domain(domain) is True


@requires_real_turbo_fieldfare_binary_and_model
def test_real_self_play_rollout_with_real_dspy_policy_produces_real_valid_zero_sum_episode(
    real_dspy_lm,
):
    from autofde_lab.hub.domain.rock_paper_scissors import RockPaperScissors
    from autofde_lab.hub.domain.rock_paper_scissors.rock_paper_scissors import Move
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy
    from autofde_lab.self_play import self_play_rollout

    max_steps = 2

    def domain_factory():
        return RockPaperScissors(max_moves=max_steps)

    with DSPyPolicy(domain_factory=domain_factory, lm=real_dspy_lm) as solver:
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
