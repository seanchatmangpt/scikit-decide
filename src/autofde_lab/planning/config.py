"""TOML schema for declaring external planner/validator engines.

Mirrors mfw-planner's ``engines.toml`` shape exactly (see
``/Users/sac/mfw/mfw-planner/engines.toml``):

    [classical]
    program = "fast-downward.py"
    args = ["--plan-file", "{plan}", "--alias", "lama-first", "{domain}", "{problem}"]
    version_args = ["--help"]
    output_mode = "file"      # "file" | "stdout" | "none"
    success_codes = [0]

``args``/``version_args`` are passed directly to a subprocess argv list — no shell is
involved anywhere in this module, matching the header comment in the source
``engines.toml``: "Every argument is passed directly to Command; no shell is involved."
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - only exercised on Python < 3.11
    import tomli as tomllib


class OutputMode(str, Enum):
    """Where the engine's result is found after a run."""

    FILE = "file"
    STDOUT = "stdout"
    NONE = "none"


class EngineConfigError(ValueError):
    """Raised when ``engines.toml`` is malformed or references an unknown role."""


PLACEHOLDERS = ("{domain}", "{problem}", "{plan}")


@dataclass(frozen=True)
class EngineConfig:
    """One ``[role]`` table from ``engines.toml``."""

    role: str
    program: str
    args: tuple[str, ...] = field(default_factory=tuple)
    version_args: tuple[str, ...] = field(default_factory=tuple)
    output_mode: OutputMode = OutputMode.NONE
    success_codes: tuple[int, ...] = (0,)

    @classmethod
    def _from_table(cls, role: str, table: dict) -> "EngineConfig":
        missing = [k for k in ("program",) if k not in table]
        if missing:
            raise EngineConfigError(
                f"engine role {role!r} missing required key(s): {missing}"
            )
        return cls(
            role=role,
            program=str(table["program"]),
            args=tuple(str(a) for a in table.get("args", [])),
            version_args=tuple(str(a) for a in table.get("version_args", [])),
            output_mode=OutputMode(table.get("output_mode", "none")),
            success_codes=tuple(int(c) for c in table.get("success_codes", [0])),
        )

    def resolve_args(
        self,
        *,
        domain: str | Path | None = None,
        problem: str | Path | None = None,
        plan: str | Path | None = None,
    ) -> list[str]:
        """Substitute ``{domain}``/``{problem}``/``{plan}`` placeholders in ``args``.

        Raises ``EngineConfigError`` if a placeholder is present but no value was
        supplied for it — a silent empty-string substitution would turn a
        misconfiguration into a confusing downstream subprocess failure instead of a
        clear one here.
        """
        values = {"{domain}": domain, "{problem}": problem, "{plan}": plan}
        resolved: list[str] = []
        for arg in self.args:
            out = arg
            for placeholder, value in values.items():
                if placeholder in out:
                    if value is None:
                        raise EngineConfigError(
                            f"engine role {self.role!r}: arg {arg!r} needs "
                            f"{placeholder}, none was supplied"
                        )
                    out = out.replace(placeholder, str(value))
            resolved.append(out)
        return resolved


@dataclass(frozen=True)
class EnginesConfig:
    """The full parsed ``engines.toml`` — a mapping of role name to ``EngineConfig``."""

    engines: dict[str, EngineConfig]

    @classmethod
    def load(cls, path: str | Path) -> "EnginesConfig":
        path = Path(path)
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        engines = {
            role: EngineConfig._from_table(role, table) for role, table in data.items()
        }
        return cls(engines=engines)

    def get(self, role: str) -> EngineConfig:
        try:
            return self.engines[role]
        except KeyError as exc:
            known = sorted(self.engines)
            raise EngineConfigError(
                f"unknown engine role {role!r}; configured roles: {known}"
            ) from exc

    def __contains__(self, role: str) -> bool:
        return role in self.engines

    def __iter__(self):
        return iter(self.engines)
