"""Chicago-style test: a REAL LLM agent (local TurboFieldfare / Gemma 4 26B-A4B
server, ``~/turbo-fieldfare``) picks the winner between candidate plan runs using
real OCEL-derived performance data — no mocked HTTP, no fabricated model reply.

Skips (named, not silent) if no TurboFieldfare server is reachable at
``http://127.0.0.1:8080`` — this keeps the suite runnable on a machine without the
model server up, per turbo-fieldfare's own "read-only to the outside world, downstream
consumer runs the tool loop" boundary: this test IS that downstream consumer.

Reuses the same real astar-optimal / naive-worse candidates as
``test_ocel_optimization_agent.py`` so the LLM's real answer can be checked against
the same ground truth the deterministic agent already gets right.
"""

from __future__ import annotations

import pytest

from autofde_lab.receipts.llm_agent import LLMOptimizationAgent, is_server_available
from autofde_lab.receipts.ocel_adapter import trajectory_to_ocel_log
from autofde_lab.standing import Blocked

from autofde_lab.receipts.tests.test_ocel_optimization_agent import (
    _astar_optimal_steps,
    _naive_worse_steps,
)

pytestmark = pytest.mark.skipif(
    not is_server_available(),
    reason="no TurboFieldfare server reachable at http://127.0.0.1:8080; "
    "start it per ~/turbo-fieldfare/docs/OPENAI_SERVER.md",
)


def _real_candidates() -> dict:
    astar_steps = _astar_optimal_steps()
    naive_steps = _naive_worse_steps()
    return {
        "astar-optimal": trajectory_to_ocel_log(astar_steps, run_id="astar-optimal"),
        "naive-worse": trajectory_to_ocel_log(naive_steps, run_id="naive-worse"),
    }


def test_llm_agent_picks_the_real_cheaper_candidate() -> None:
    agent = LLMOptimizationAgent()
    decision = agent.select_best(_real_candidates())

    assert decision.winner_run_id == "astar-optimal"
    assert decision.reason  # the model's own real stated reason, non-empty
    by_id = {s.run_id: s for s in decision.scores}
    assert by_id["astar-optimal"].total_cost == 4
    assert by_id["naive-worse"].total_cost == 6


def test_llm_agent_refuses_an_empty_candidate_set_without_calling_the_server() -> None:
    with pytest.raises(Blocked, match="no candidate OCEL logs"):
        LLMOptimizationAgent().select_best({})


def test_is_server_available_reflects_the_real_health_endpoint() -> None:
    assert is_server_available() is True
    assert is_server_available(base_url="http://127.0.0.1:1/v1", timeout=0.5) is False
