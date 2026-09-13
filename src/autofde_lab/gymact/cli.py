"""Real Typer CLI over GymActKernel.

Mirrors `tests/fabric/test_cli.py`'s DI shape (a real, already-built kernel
object shared across invocations) without mocking Typer/Click itself.
"""

from __future__ import annotations

import uuid

import typer

from autofde_lab.gymact.kernel import OPERATIONS, GymActKernel

app = typer.Typer(name="gymact")
_kernel = GymActKernel()


@app.command("discover")
def discover_command() -> None:
    """List the GymAct kernel lifecycle operations."""
    for operation in OPERATIONS:
        typer.echo(operation)


@app.command("act")
def act_command(subject: str = typer.Option(..., "--subject")) -> None:
    """Actuate a real GymActKernel intent."""
    episode_id = str(uuid.uuid4())
    result = _kernel.act(subject=subject, episode_id=episode_id)
    typer.echo(f"{result.standing} episode={result.episode_id}")
