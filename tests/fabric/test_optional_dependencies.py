from __future__ import annotations

import pytest

from autofde_lab.fabric.service import DecisionFabric


def test_fastmcp_server_constructs_with_real_sdk() -> None:
    pytest.importorskip("fastmcp")
    from autofde_lab.fabric.mcp import create_server

    assert create_server() is not None


def test_a2a_application_constructs_with_real_sdk() -> None:
    pytest.importorskip("a2a")
    from autofde_lab.fabric.a2a import create_app

    app = create_app(url="http://127.0.0.1:9999")
    assert app is not None


def test_dspy_compiler_constructs_without_invoking_an_lm() -> None:
    pytest.importorskip("dspy")
    from autofde_lab.fabric.dspy import DSPyDecisionCompiler

    assert DSPyDecisionCompiler() is not None


def test_default_fabric_constructs_without_loading_a_solver() -> None:
    fabric = DecisionFabric()
    assert fabric is not None
    fabric.cache.close()
