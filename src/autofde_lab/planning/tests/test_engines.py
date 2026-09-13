"""Checkpoint A verification: positive + negative fixtures for
``autofde_lab.planning``'s declarative engine config + shell-free runner.

Positive: a real config parse + a successful run against the fake engine, producing a
plan file with a non-None hash.

Negative: missing binary, non-zero exit, timeout, and success-with-no-output each
produce their own distinct, receipted ``EngineOutcome`` — never a bare exception, per
the plan's requirement.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from autofde_lab.planning.config import EngineConfig, EnginesConfig, OutputMode
from autofde_lab.planning.runner import EngineOutcome, probe_engine, run_engine

FIXTURES = Path(__file__).parent / "fixtures"
DOMAIN = FIXTURES / "blocks-domain.pddl"
PROBLEM = FIXTURES / "blocks-problem.pddl"
FAKE_ENGINE = FIXTURES / "fake_engine.py"


def _fake_cfg(role: str, mode: str, *, output_mode: OutputMode) -> EngineConfig:
    args = ["--mode", mode]
    if output_mode == OutputMode.FILE:
        args += ["--plan-file", "{plan}"]
    args += ["{domain}", "{problem}"]
    return EngineConfig(
        role=role,
        program=sys.executable,
        args=tuple([str(FAKE_ENGINE), *args]),
        version_args=("--help",),
        output_mode=output_mode,
        success_codes=(0,),
    )


# ---------------------------------------------------------------------------
# EnginesConfig.load / EngineConfig.resolve_args — parsing behavior
# ---------------------------------------------------------------------------


def test_load_parses_engines_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "engines.toml"
    toml_path.write_text(
        textwrap.dedent(
            """
            [classical]
            program = "fast-downward.py"
            args = ["--plan-file", "{plan}", "{domain}", "{problem}"]
            version_args = ["--help"]
            output_mode = "file"
            success_codes = [0]
            """
        )
    )
    cfg = EnginesConfig.load(toml_path)
    assert "classical" in cfg
    engine = cfg.get("classical")
    assert engine.program == "fast-downward.py"
    assert engine.output_mode == OutputMode.FILE
    assert engine.success_codes == (0,)


def test_load_the_real_shipped_engines_toml() -> None:
    cfg = EnginesConfig.load(Path(__file__).parents[1] / "engines.toml")
    assert set(cfg.engines) == {"classical", "validator"}
    assert cfg.get("classical").output_mode == OutputMode.FILE
    assert cfg.get("validator").output_mode == OutputMode.NONE


def test_unknown_role_raises_with_known_roles_listed(tmp_path: Path) -> None:
    toml_path = tmp_path / "engines.toml"
    toml_path.write_text('[classical]\nprogram = "x"\n')
    cfg = EnginesConfig.load(toml_path)
    with pytest.raises(Exception, match="unknown engine role"):
        cfg.get("nope")


def test_resolve_args_requires_a_value_for_each_placeholder_present() -> None:
    engine = EngineConfig(role="r", program="x", args=("{plan}",))
    with pytest.raises(Exception, match=r"needs \{plan\}"):
        engine.resolve_args(domain="d", problem="p")  # no plan supplied


# ---------------------------------------------------------------------------
# Positive fixture: full success run against the fake engine
# ---------------------------------------------------------------------------


def test_run_engine_success_hashes_the_produced_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    cfg = _fake_cfg("classical", "success", output_mode=OutputMode.FILE)
    receipt = run_engine(cfg, domain=DOMAIN, problem=PROBLEM, plan=plan_path)
    assert receipt.outcome == EngineOutcome.SUCCESS
    assert receipt.is_success()
    assert receipt.exit_code == 0
    assert receipt.plan_hash is not None
    assert plan_path.exists()


def test_probe_engine_succeeds_for_a_real_interpreter() -> None:
    cfg = _fake_cfg("classical", "success", output_mode=OutputMode.FILE)
    receipt = probe_engine(cfg)
    assert receipt.outcome == EngineOutcome.SUCCESS


# ---------------------------------------------------------------------------
# Negative fixtures — each must produce its own distinct EngineOutcome, not a
# bare exception.
# ---------------------------------------------------------------------------


def test_missing_binary_is_a_receipted_outcome_not_an_exception() -> None:
    cfg = EngineConfig(
        role="ghost",
        program="/definitely/not/a/real/binary/xyz",
        args=(),
        output_mode=OutputMode.NONE,
    )
    receipt = run_engine(cfg, domain=DOMAIN, problem=PROBLEM)
    assert receipt.outcome == EngineOutcome.MISSING_BINARY
    assert not receipt.is_success()


def test_probe_engine_missing_binary_is_also_a_receipted_outcome() -> None:
    cfg = EngineConfig(
        role="ghost",
        program="/definitely/not/a/real/binary/xyz",
        args=(),
        version_args=("--help",),
        output_mode=OutputMode.NONE,
    )
    receipt = probe_engine(cfg)
    assert receipt.outcome == EngineOutcome.MISSING_BINARY
    assert not receipt.is_success()


def test_nonzero_exit_is_tool_failed(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    cfg = _fake_cfg("classical", "tool_failed", output_mode=OutputMode.FILE)
    receipt = run_engine(cfg, domain=DOMAIN, problem=PROBLEM, plan=plan_path)
    assert receipt.outcome == EngineOutcome.TOOL_FAILED
    assert receipt.exit_code == 1
    assert receipt.plan_hash is None


def test_success_exit_with_no_plan_file_is_no_candidate(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    cfg = _fake_cfg("classical", "no_candidate", output_mode=OutputMode.FILE)
    receipt = run_engine(cfg, domain=DOMAIN, problem=PROBLEM, plan=plan_path)
    assert receipt.outcome == EngineOutcome.NO_CANDIDATE
    assert receipt.exit_code == 0
    assert receipt.plan_hash is None
    assert not plan_path.exists()


def test_timeout_is_bounded_not_a_crash(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    cfg = _fake_cfg("classical", "bounded", output_mode=OutputMode.FILE)
    receipt = run_engine(
        cfg, domain=DOMAIN, problem=PROBLEM, plan=plan_path, timeout_s=0.5
    )
    assert receipt.outcome == EngineOutcome.BOUNDED
    assert receipt.exit_code is None
