"""Typed admission of the ambient sibling/local dependencies Level 4 relies on.

Why this module exists
----------------------
``uv run`` currently succeeds only because an editable sibling checkout happens to
exist on this machine at ``/Users/sac/wasm4pm-compat/python`` (and another at
``/Users/sac/gymact``). **Directory exists is not standing.** A path that resolves
is filesystem adjacency, not identity -- the same class of error
``.claude/rules/no-dual-bookkeeping.md`` names for artifacts sharing a directory.

So this module refuses to answer "is the dependency there?" and instead answers a
question that can actually be falsified:

    Is the *identity* of the thing on disk established, and does the module that
    Python actually imports come from *that* checkout?

Every answer is a typed outcome. There is no boolean anywhere on the admission
surface, and :class:`DependencyAdmission` deliberately raises on ``__bool__`` so it
can never be collapsed into a truthy summary field.

The three outcomes
------------------
``ADMITTED_DEPENDENCY``
    Every identity relation was established from primary evidence: a real
    ``git rev-parse HEAD`` on a clean worktree, a real remote URL matching the
    declared repository, a real import whose resolved ``__file__`` lies under that
    same checkout.

``UNSUPPORTED:DEPENDENCY_ABSENT``
    The declared artifact is not present at all. This is a capability gap, not
    incomplete evidence -- the ``UNSUPPORTED`` sense of
    ``.claude/rules/standing-law.md``.

``UNKNOWN:DEPENDENCY_IDENTITY_UNPROVEN``
    Something is present, but the required identity relation is *not established*.
    A dirty worktree has no identity: it corresponds to no recorded revision, so
    "the SHA" names a tree that does not exist on disk. A package whose import
    resolves outside the declared checkout is a different artifact wearing the
    right name.

``UNKNOWN`` is never coerced into an absence and absence is never coerced into
``UNKNOWN``; per ``.claude/rules/absence-is-not-evidence.md`` they are different
observations and both survive projection.

Discovery, not assumption
-------------------------
:func:`declared_uv_sources` reads ``[tool.uv.sources]`` out of the real
``pyproject.toml`` with ``tomllib``. The declared set is discovered from the
project file rather than hard-coded, so a source added later cannot silently
escape admission.
"""

from __future__ import annotations

import hashlib
import importlib
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "DependencyKind",
    "DependencyOutcome",
    "UnprovenReason",
    "AbsenceReason",
    "DependencyDeclaration",
    "CheckoutIdentity",
    "ImportIdentity",
    "DependencyAdmission",
    "declared_uv_sources",
    "level4_dependency_declarations",
    "probe_checkout",
    "probe_import",
    "admit_dependency",
    "admit_level4_dependencies",
    "REPO_ROOT",
]

REPO_ROOT = Path(__file__).resolve().parents[5]


class DependencyKind(str, Enum):
    """What sort of artifact the declaration names."""

    EDITABLE_PYTHON_PACKAGE = "EDITABLE_PYTHON_PACKAGE"
    BINARY_ARTIFACT = "BINARY_ARTIFACT"


class DependencyOutcome(str, Enum):
    """The only three admissible answers. No boolean equivalent exists."""

    ADMITTED_DEPENDENCY = "ADMITTED_DEPENDENCY"
    UNSUPPORTED_DEPENDENCY_ABSENT = "UNSUPPORTED:DEPENDENCY_ABSENT"
    UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN = "UNKNOWN:DEPENDENCY_IDENTITY_UNPROVEN"


class AbsenceReason(str, Enum):
    """Why an ``UNSUPPORTED:DEPENDENCY_ABSENT`` was issued."""

    CHECKOUT_PATH_ABSENT = "CHECKOUT_PATH_ABSENT"
    BINARY_ABSENT = "BINARY_ABSENT"
    BINARY_NOT_EXECUTABLE = "BINARY_NOT_EXECUTABLE"


class UnprovenReason(str, Enum):
    """Why an ``UNKNOWN:DEPENDENCY_IDENTITY_UNPROVEN`` was issued.

    Each names the *specific* relation that was not established, so the gap is
    never reported as an undifferentiated failure.
    """

    NO_GIT_METADATA = "NO_GIT_METADATA"
    GIT_UNAVAILABLE = "GIT_UNAVAILABLE"
    NO_RECORDED_REVISION = "NO_RECORDED_REVISION"
    WORKTREE_DIRTY = "WORKTREE_DIRTY"
    NO_REMOTE_DECLARED = "NO_REMOTE_DECLARED"
    REPOSITORY_IDENTITY_MISMATCH = "REPOSITORY_IDENTITY_MISMATCH"
    IMPORT_UNRESOLVABLE = "IMPORT_UNRESOLVABLE"
    IMPORT_HAS_NO_FILE = "IMPORT_HAS_NO_FILE"
    IMPORT_PATH_NOT_UNDER_CHECKOUT = "IMPORT_PATH_NOT_UNDER_CHECKOUT"


@dataclass(frozen=True)
class DependencyDeclaration:
    """What we *expect* -- the declared side of the relation.

    Nothing here is evidence. It is the claim that :func:`admit_dependency`
    attempts, and may fail, to discharge against the machine.
    """

    package_identity: str
    kind: DependencyKind
    checkout_path: Path
    expected_repository: str | None = None
    import_identity: str | None = None
    binary_relative_path: str | None = None
    compatibility_expectation: str = ""

    @property
    def declaration_id(self) -> str:
        if self.binary_relative_path is not None:
            return f"{self.package_identity}::{self.binary_relative_path}"
        return self.package_identity


@dataclass(frozen=True)
class CheckoutIdentity:
    """Primary evidence read off the checkout itself."""

    path: Path
    path_exists: bool
    is_git_repository: bool
    head_sha: str | None
    remote_url: str | None
    dirty_entries: tuple[str, ...] = ()

    @property
    def dirty_entry_count(self) -> int:
        return len(self.dirty_entries)


@dataclass(frozen=True)
class ImportIdentity:
    """Where Python *actually* imports the module from, resolved for real."""

    module_name: str
    resolved: bool
    module_file: Path | None
    failure: str | None = None


@dataclass(frozen=True)
class DependencyAdmission:
    """A typed admission decision. Never a boolean, never a score."""

    declaration: DependencyDeclaration
    outcome: DependencyOutcome
    checkout: CheckoutIdentity | None = None
    imported: ImportIdentity | None = None
    absence_reason: AbsenceReason | None = None
    unproven_reasons: tuple[UnprovenReason, ...] = ()
    detail: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:  # pragma: no cover - exercised by the test suite
        raise TypeError(
            "DependencyAdmission has no truth value: ADMITTED_DEPENDENCY, "
            "UNSUPPORTED:DEPENDENCY_ABSENT and UNKNOWN:DEPENDENCY_IDENTITY_UNPROVEN "
            "are three distinct outcomes and collapsing them into a boolean "
            "manufactures standing from absence. Compare .outcome explicitly."
        )

    @property
    def recorded_revision(self) -> str | None:
        """The SHA *only when it names the tree on disk* -- else ``None``.

        A dirty worktree corresponds to no recorded revision, so exposing its
        HEAD as "the revision" would be exactly the coincidence-into-semantics
        move the completion law forbids.
        """
        if self.checkout is None or self.checkout.dirty_entries:
            return None
        return self.checkout.head_sha


def _git(path: Path, *args: str) -> tuple[int, str]:
    """Run a real ``git`` subprocess against ``path``. No mocking, ever."""
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def probe_checkout(path: Path, remote_name: str = "origin") -> CheckoutIdentity:
    """Read identity evidence off a real directory with real git."""
    if not path.exists():
        return CheckoutIdentity(
            path=path,
            path_exists=False,
            is_git_repository=False,
            head_sha=None,
            remote_url=None,
        )

    rc_top, top = _git(path, "rev-parse", "--show-toplevel")
    if rc_top != 0:
        return CheckoutIdentity(
            path=path,
            path_exists=True,
            is_git_repository=False,
            head_sha=None,
            remote_url=None,
        )

    rc_head, head = _git(path, "rev-parse", "HEAD")
    rc_remote, remote = _git(path, "remote", "get-url", remote_name)
    rc_status, status = _git(path, "status", "--porcelain")
    dirty = tuple(line for line in status.splitlines() if line.strip()) if rc_status == 0 else ()

    return CheckoutIdentity(
        path=path,
        path_exists=True,
        is_git_repository=True,
        head_sha=head if rc_head == 0 and head else None,
        remote_url=remote if rc_remote == 0 and remote else None,
        dirty_entries=dirty,
    )


def probe_import(module_name: str) -> ImportIdentity:
    """Import for real and report where the interpreter actually found it."""
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - the failure text is the evidence
        return ImportIdentity(
            module_name=module_name,
            resolved=False,
            module_file=None,
            failure=f"{type(exc).__name__}: {exc}",
        )
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        return ImportIdentity(
            module_name=module_name,
            resolved=True,
            module_file=None,
            failure="module has no __file__",
        )
    return ImportIdentity(
        module_name=module_name,
        resolved=True,
        module_file=Path(module_file).resolve(),
    )


def _normalise_remote(url: str) -> str:
    url = url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@") and ":" in url:
        host, _, tail = url[len("git@") :].partition(":")
        url = f"https://{host}/{tail}"
    return url.rstrip("/").lower()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _admit_binary(declaration: DependencyDeclaration) -> DependencyAdmission:
    assert declaration.binary_relative_path is not None
    binary = declaration.checkout_path / declaration.binary_relative_path
    if not binary.exists():
        return DependencyAdmission(
            declaration=declaration,
            outcome=DependencyOutcome.UNSUPPORTED_DEPENDENCY_ABSENT,
            absence_reason=AbsenceReason.BINARY_ABSENT,
            detail=(f"no artifact at {binary}",),
        )
    import os

    if not os.access(binary, os.X_OK):
        return DependencyAdmission(
            declaration=declaration,
            outcome=DependencyOutcome.UNSUPPORTED_DEPENDENCY_ABSENT,
            absence_reason=AbsenceReason.BINARY_NOT_EXECUTABLE,
            detail=(f"{binary} exists but is not executable",),
        )

    checkout = probe_checkout(declaration.checkout_path)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    detail = (f"artifact sha256={digest}", f"size={binary.stat().st_size}")
    reasons = _identity_reasons(declaration, checkout)
    if reasons:
        return DependencyAdmission(
            declaration=declaration,
            outcome=DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN,
            checkout=checkout,
            unproven_reasons=reasons,
            detail=detail,
        )
    return DependencyAdmission(
        declaration=declaration,
        outcome=DependencyOutcome.ADMITTED_DEPENDENCY,
        checkout=checkout,
        detail=detail,
    )


def _identity_reasons(
    declaration: DependencyDeclaration, checkout: CheckoutIdentity
) -> tuple[UnprovenReason, ...]:
    reasons: list[UnprovenReason] = []
    if not checkout.is_git_repository:
        reasons.append(UnprovenReason.NO_GIT_METADATA)
        return tuple(reasons)
    if checkout.head_sha is None:
        reasons.append(UnprovenReason.NO_RECORDED_REVISION)
    if checkout.dirty_entries:
        reasons.append(UnprovenReason.WORKTREE_DIRTY)
    if declaration.expected_repository is not None:
        if checkout.remote_url is None:
            reasons.append(UnprovenReason.NO_REMOTE_DECLARED)
        elif _normalise_remote(checkout.remote_url) != _normalise_remote(
            declaration.expected_repository
        ):
            reasons.append(UnprovenReason.REPOSITORY_IDENTITY_MISMATCH)
    return tuple(reasons)


def admit_dependency(declaration: DependencyDeclaration) -> DependencyAdmission:
    """Discharge -- or fail to discharge -- one declaration against the machine."""
    if declaration.kind is DependencyKind.BINARY_ARTIFACT:
        return _admit_binary(declaration)

    if not declaration.checkout_path.exists():
        return DependencyAdmission(
            declaration=declaration,
            outcome=DependencyOutcome.UNSUPPORTED_DEPENDENCY_ABSENT,
            absence_reason=AbsenceReason.CHECKOUT_PATH_ABSENT,
            detail=(f"declared checkout {declaration.checkout_path} does not exist",),
        )

    checkout = probe_checkout(declaration.checkout_path)
    reasons = list(_identity_reasons(declaration, checkout))

    imported: ImportIdentity | None = None
    detail: list[str] = []
    if declaration.import_identity is not None:
        imported = probe_import(declaration.import_identity)
        if not imported.resolved:
            reasons.append(UnprovenReason.IMPORT_UNRESOLVABLE)
            detail.append(str(imported.failure))
        elif imported.module_file is None:
            reasons.append(UnprovenReason.IMPORT_HAS_NO_FILE)
        elif not _is_under(imported.module_file, declaration.checkout_path):
            reasons.append(UnprovenReason.IMPORT_PATH_NOT_UNDER_CHECKOUT)
            detail.append(
                f"{declaration.import_identity} resolves to {imported.module_file}, "
                f"which is not under declared checkout {declaration.checkout_path}"
            )

    if reasons:
        return DependencyAdmission(
            declaration=declaration,
            outcome=DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN,
            checkout=checkout,
            imported=imported,
            unproven_reasons=tuple(reasons),
            detail=tuple(detail),
        )
    return DependencyAdmission(
        declaration=declaration,
        outcome=DependencyOutcome.ADMITTED_DEPENDENCY,
        checkout=checkout,
        imported=imported,
        detail=tuple(detail),
    )


def declared_uv_sources(pyproject: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read ``[tool.uv.sources]`` out of the real ``pyproject.toml``.

    Discovery, not assumption: a source added to the project later shows up here
    without this module being edited.
    """
    path = pyproject if pyproject is not None else REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    return {name: dict(spec) for name, spec in sources.items()}


#: Import identity per declared uv source. Recorded here because a distribution
#: name does not determine a module name (``wasm4pm-compat-pydantic`` imports as
#: ``wasm4pm_compat_pydantic``), and the mapping is a claim we want checked.
_IMPORT_IDENTITY: dict[str, str] = {
    "wasm4pm-compat-pydantic": "wasm4pm_compat_pydantic",
    "gymact": "gymact",
}

_EXPECTED_REPOSITORY: dict[str, str] = {
    "wasm4pm-compat-pydantic": "https://github.com/seanchatmangpt/wasm4pm-compat.git",
    "gymact": "https://github.com/seanchatmangpt/gymact.git",
}

_COMPATIBILITY: dict[str, str] = {
    "wasm4pm-compat-pydantic": (
        "pure-pydantic typed process-mining observation shapes consumed by "
        "autofde_lab.receipts.wasm4pm_types; no native/Rust dependency"
    ),
    "gymact": (
        "requires-python >=3.11,<4.0 while this project declares >=3.10, so the "
        "project dependency carries a python_version >= '3.11' marker; imported at "
        "module level by src/autofde_lab/gymact/kernel.py"
    ),
}

#: The ``wpm`` binaries are not a uv source -- they are ambient build artifacts of
#: a sibling Rust repository -- so they are declared explicitly rather than
#: discovered. Their absence must be expressible, which is why they are modelled
#: at all instead of assumed present.
WPM_REPO = Path("/Users/sac/wasm4pm")
_WPM_PROFILES = ("debug", "release")


def level4_dependency_declarations(
    pyproject: Path | None = None,
) -> tuple[DependencyDeclaration, ...]:
    """The real declared set: every uv source, plus the ``wpm`` binaries."""
    declarations: list[DependencyDeclaration] = []
    for name, spec in sorted(declared_uv_sources(pyproject).items()):
        raw_path = spec.get("path")
        if raw_path is None:
            # A non-path source (git/url/index) is a different identity question
            # than a local checkout; it is not silently folded in here.
            continue
        declarations.append(
            DependencyDeclaration(
                package_identity=name,
                kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
                checkout_path=Path(raw_path),
                expected_repository=_EXPECTED_REPOSITORY.get(name),
                import_identity=_IMPORT_IDENTITY.get(name),
                compatibility_expectation=_COMPATIBILITY.get(name, ""),
            )
        )
    for profile in _WPM_PROFILES:
        declarations.append(
            DependencyDeclaration(
                package_identity="wpm",
                kind=DependencyKind.BINARY_ARTIFACT,
                checkout_path=WPM_REPO,
                expected_repository="https://github.com/seanchatmangpt/wasm4pm.git",
                binary_relative_path=f"target/{profile}/wpm",
                compatibility_expectation=(
                    f"wasm4pm-cli {profile} build; discovery/conformance backend "
                    "invoked as a real subprocess"
                ),
            )
        )
    return tuple(declarations)


def admit_level4_dependencies(
    pyproject: Path | None = None,
) -> tuple[DependencyAdmission, ...]:
    """Admit every declared Level 4 dependency, for real, right now."""
    return tuple(
        admit_dependency(declaration)
        for declaration in level4_dependency_declarations(pyproject)
    )


def render_table(admissions: tuple[DependencyAdmission, ...]) -> str:
    """A *reporting projection* -- never an input to any standing decision."""
    lines = []
    for adm in admissions:
        d = adm.declaration
        lines.append(f"{d.declaration_id}")
        lines.append(f"    outcome          : {adm.outcome.value}")
        lines.append(f"    checkout path    : {d.checkout_path}")
        lines.append(f"    expected repo    : {d.expected_repository}")
        lines.append(f"    package identity : {d.package_identity}")
        lines.append(f"    import identity  : {d.import_identity}")
        if adm.checkout is not None:
            lines.append(f"    observed remote  : {adm.checkout.remote_url}")
            lines.append(f"    HEAD             : {adm.checkout.head_sha}")
            lines.append(f"    dirty entries    : {adm.checkout.dirty_entry_count}")
        lines.append(f"    recorded revision: {adm.recorded_revision}")
        if adm.imported is not None:
            lines.append(f"    import resolves  : {adm.imported.module_file}")
        if adm.absence_reason is not None:
            lines.append(f"    absence reason   : {adm.absence_reason.value}")
        if adm.unproven_reasons:
            lines.append(
                "    unproven reasons : "
                + ", ".join(r.value for r in adm.unproven_reasons)
            )
        for extra in adm.detail:
            lines.append(f"    detail           : {extra}")
        lines.append(f"    compatibility    : {d.compatibility_expectation}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    sys.stdout.write(render_table(admit_level4_dependencies()))
