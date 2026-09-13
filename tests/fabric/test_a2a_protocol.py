from __future__ import annotations

from autofde_lab.fabric.a2a import DecisionAgentProtocol
from autofde_lab.fabric.service import DecisionFabric


def test_a2a_protocol_executes_json_without_llm(fabric: DecisionFabric) -> None:
    protocol = DecisionAgentProtocol(fabric)

    result = protocol.handle_text(
        '{"domain":"Counter","domain_arguments":{"limit":1},"max_steps":2}'
    )

    assert result["standing"] == "SOLVED"
    assert result["cache_status"] == "BYPASS"
    assert result["request"]["domain"] == "Counter"


def test_a2a_protocol_returns_typed_refusal(fabric: DecisionFabric) -> None:
    result = DecisionAgentProtocol(fabric).handle_text("not json")

    assert result["standing"] == "REFUSED"
    assert result["code"] == "SKD-FABRIC-010"
