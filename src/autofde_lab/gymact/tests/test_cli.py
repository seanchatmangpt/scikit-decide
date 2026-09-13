"""Chicago-style TDD prep: real Typer CLI via real typer.testing.CliRunner.

`autofde_lab.gymact.cli` does not exist yet -- expected to fail at collection
until the next pass adds a real Typer `app`. Mirrors
tests/fabric/test_cli.py's dependency-injection shape (a factory override
returning an already-built real object, not a mock of Typer/Click itself);
every assertion here is on real CLI stdout/exit code.
"""

from __future__ import annotations

import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner  # noqa: E402

from autofde_lab.gymact.cli import app  # noqa: E402

runner = CliRunner()


def test_discover_lists_kernel_operations() -> None:
    result = runner.invoke(app, ["discover"])

    assert result.exit_code == 0
    assert "act" in result.stdout
    assert "observe" in result.stdout


def test_act_without_required_subject_exits_nonzero() -> None:
    result = runner.invoke(app, ["act"])

    assert result.exit_code != 0
