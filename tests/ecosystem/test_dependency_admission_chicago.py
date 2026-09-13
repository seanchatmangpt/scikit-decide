"""Chicago-style admission tests for the ambient sibling-dependency gap.

Real collaborators throughout: real ``git init``/``git commit`` subprocesses
building real repositories in real ``tmp_path`` directories, real
``importlib.import_module`` calls, real reads of this repo's real
``pyproject.toml``. No ``unittest.mock``, no ``patch``, no ``monkeypatch``
substitution of any collaborator this repo owns. Assertions are on final state
-- the typed outcome object and its typed reasons -- never on "was this called".

The hostile fixtures are the point of the file: a checkout carrying the *right
package name* and the *wrong identity* must never reach ``ADMITTED_DEPENDENCY``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.dependency_admission import (
    REPO_ROOT,
    AbsenceReason,
    CheckoutIdentity,
    DependencyDeclaration,
    DependencyKind,
    DependencyOutcome,
    UnprovenReason,
    admit_dependency,
    admit_level4_dependencies,
    declared_uv_sources,
    level4_dependency_declarations,
    probe_checkout,
)


def _run(cwd: Path, *args: str) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _make_repo(root: Path, module_name: str, body: str = "VALUE = 1\n") -> Path:
    """Build a real, clean, committed git repository containing a real package."""
    root.mkdir(parents=True, exist_ok=True)
    pkg = root / "src" / module_name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(body, encoding="utf-8")
    _run(root, "git", "init", "-q", "-b", "main")
    _run(root, "git", "config", "user.email", "test@example.invalid")
    _run(root, "git", "config", "user.name", "Test")
    _run(root, "git", "remote", "add", "origin", "https://example.invalid/real-repo.git")
    _run(root, "git", "add", "-A")
    _run(root, "git", "commit", "-q", "-m", "initial")
    return root


@pytest.fixture
def importable(tmp_path: Path):
    """Put real checkouts on ``sys.path`` and take them off again.

    This is path arrangement, not collaborator substitution -- the import that
    follows is a real ``importlib`` import of a real file on disk.
    """
    added: list[str] = []

    def _add(path: Path) -> None:
        entry = str(path / "src")
        sys.path.insert(0, entry)
        added.append(entry)

    yield _add

    for entry in added:
        while entry in sys.path:
            sys.path.remove(entry)
    for name in [n for n in sys.modules if n.startswith("depadm_")]:
        del sys.modules[name]


# --------------------------------------------------------------------------
# The declared set is discovered, not assumed
# --------------------------------------------------------------------------


def test_uv_sources_discovered_from_the_real_pyproject() -> None:
    sources = declared_uv_sources()
    assert set(sources) == {"wasm4pm-compat-pydantic", "gymact"}
    assert sources["wasm4pm-compat-pydantic"]["path"] == "/Users/sac/wasm4pm-compat/python"
    assert sources["gymact"]["path"] == "/Users/sac/gymact"
    assert (REPO_ROOT / "pyproject.toml").exists()


def test_declaration_set_covers_every_uv_source_plus_the_wpm_binaries() -> None:
    declared = level4_dependency_declarations()
    ids = {d.declaration_id for d in declared}
    assert ids == {
        "gymact",
        "wasm4pm-compat-pydantic",
        "wpm::target/debug/wpm",
        "wpm::target/release/wpm",
    }
    editable = {d.package_identity for d in declared if d.kind is DependencyKind.EDITABLE_PYTHON_PACKAGE}
    assert editable == set(declared_uv_sources())


def test_gymact_declaration_records_its_real_module_level_import_site() -> None:
    kernel = REPO_ROOT / "src" / "autofde_lab" / "gymact" / "kernel.py"
    text = kernel.read_text(encoding="utf-8")
    assert "from gymact.models import ActuationIntent" in text
    assert "from gymact.runtime import GymAct" in text
    decl = next(d for d in level4_dependency_declarations() if d.package_identity == "gymact")
    assert decl.import_identity == "gymact"


# --------------------------------------------------------------------------
# No booleans on the admission surface
# --------------------------------------------------------------------------


def test_admission_refuses_to_be_a_boolean() -> None:
    admission = admit_level4_dependencies()[0]
    with pytest.raises(TypeError, match="no truth value"):
        bool(admission)


def test_the_three_outcomes_are_distinct_values() -> None:
    values = {o.value for o in DependencyOutcome}
    assert values == {
        "ADMITTED_DEPENDENCY",
        "UNSUPPORTED:DEPENDENCY_ABSENT",
        "UNKNOWN:DEPENDENCY_IDENTITY_UNPROVEN",
    }


# --------------------------------------------------------------------------
# A clean, real, matching checkout is admissible -- so the type can be reached
# --------------------------------------------------------------------------


def test_clean_matching_checkout_is_admitted(tmp_path: Path, importable) -> None:
    repo = _make_repo(tmp_path / "real", "depadm_real")
    importable(repo)
    decl = DependencyDeclaration(
        package_identity="depadm-real",
        kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
        checkout_path=repo,
        expected_repository="https://example.invalid/real-repo.git",
        import_identity="depadm_real",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.ADMITTED_DEPENDENCY
    assert admission.unproven_reasons == ()
    real_head = _run(repo, "git", "rev-parse", "HEAD")
    assert admission.recorded_revision == real_head
    assert admission.imported is not None
    assert admission.imported.module_file == (repo / "src" / "depadm_real" / "__init__.py").resolve()


# --------------------------------------------------------------------------
# HOSTILE FIXTURE 1: right package name, different checkout identity (git repo
# at a different SHA / different remote)
# --------------------------------------------------------------------------


def test_hostile_same_name_different_repository_is_never_admitted(
    tmp_path: Path, importable
) -> None:
    impostor = _make_repo(tmp_path / "impostor", "depadm_real", body="VALUE = 999\n")
    _run(impostor, "git", "remote", "set-url", "origin", "https://example.invalid/OTHER.git")
    importable(impostor)

    decl = DependencyDeclaration(
        package_identity="depadm-real",
        kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
        checkout_path=impostor,
        expected_repository="https://example.invalid/real-repo.git",
        import_identity="depadm_real",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN
    assert UnprovenReason.REPOSITORY_IDENTITY_MISMATCH in admission.unproven_reasons
    assert admission.checkout is not None
    assert admission.checkout.head_sha == _run(impostor, "git", "rev-parse", "HEAD")


def test_hostile_import_resolves_outside_the_declared_checkout(
    tmp_path: Path, importable
) -> None:
    """The declared checkout is real and clean; the *import* comes from elsewhere.

    This is the exact ambient failure: two directories, right name in both, and
    the interpreter silently picks the one nobody declared.
    """
    declared = _make_repo(tmp_path / "declared", "depadm_two")
    elsewhere = _make_repo(tmp_path / "elsewhere", "depadm_two", body="VALUE = 2\n")
    importable(elsewhere)  # shadows first -- inserted at sys.path[0]

    decl = DependencyDeclaration(
        package_identity="depadm-two",
        kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
        checkout_path=declared,
        expected_repository="https://example.invalid/real-repo.git",
        import_identity="depadm_two",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN
    assert UnprovenReason.IMPORT_PATH_NOT_UNDER_CHECKOUT in admission.unproven_reasons
    assert admission.imported is not None
    assert admission.imported.module_file is not None
    assert str(elsewhere) in str(admission.imported.module_file)


def test_hostile_right_name_no_git_metadata_is_unknown_not_admitted(
    tmp_path: Path, importable
) -> None:
    plain = tmp_path / "plain"
    pkg = plain / "src" / "depadm_plain"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VALUE = 3\n", encoding="utf-8")
    importable(plain)

    decl = DependencyDeclaration(
        package_identity="depadm-plain",
        kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
        checkout_path=plain,
        expected_repository="https://example.invalid/real-repo.git",
        import_identity="depadm_plain",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN
    assert admission.unproven_reasons == (UnprovenReason.NO_GIT_METADATA,)
    assert admission.recorded_revision is None


# --------------------------------------------------------------------------
# A dirty tree has no identity
# --------------------------------------------------------------------------


def test_dirty_worktree_has_no_recorded_revision(tmp_path: Path, importable) -> None:
    repo = _make_repo(tmp_path / "dirty", "depadm_dirty")
    (repo / "src" / "depadm_dirty" / "extra.py").write_text("X = 1\n", encoding="utf-8")
    importable(repo)

    decl = DependencyDeclaration(
        package_identity="depadm-dirty",
        kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
        checkout_path=repo,
        expected_repository="https://example.invalid/real-repo.git",
        import_identity="depadm_dirty",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN
    assert UnprovenReason.WORKTREE_DIRTY in admission.unproven_reasons
    assert admission.checkout is not None
    assert admission.checkout.head_sha is not None  # HEAD exists ...
    assert admission.recorded_revision is None  # ... but names no tree on disk


# --------------------------------------------------------------------------
# Absence is not UNKNOWN, and UNKNOWN is not absence
# --------------------------------------------------------------------------


def test_absent_checkout_is_unsupported_not_unknown(tmp_path: Path) -> None:
    decl = DependencyDeclaration(
        package_identity="depadm-gone",
        kind=DependencyKind.EDITABLE_PYTHON_PACKAGE,
        checkout_path=tmp_path / "definitely-not-here",
        expected_repository="https://example.invalid/real-repo.git",
        import_identity="depadm_gone",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.UNSUPPORTED_DEPENDENCY_ABSENT
    assert admission.absence_reason is AbsenceReason.CHECKOUT_PATH_ABSENT
    assert admission.unproven_reasons == ()


def test_absent_binary_is_unsupported(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "bin", "depadm_bin")
    decl = DependencyDeclaration(
        package_identity="wpm",
        kind=DependencyKind.BINARY_ARTIFACT,
        checkout_path=repo,
        binary_relative_path="target/release/wpm",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.UNSUPPORTED_DEPENDENCY_ABSENT
    assert admission.absence_reason is AbsenceReason.BINARY_ABSENT


def test_present_binary_in_clean_repo_is_admitted_with_a_real_digest(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path / "binok", "depadm_binok")
    target = repo / "target" / "release"
    target.mkdir(parents=True)
    binary = target / "wpm"
    binary.write_bytes(b"#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    _run(repo, "git", "add", "-A")
    _run(repo, "git", "commit", "-q", "-m", "binary")

    decl = DependencyDeclaration(
        package_identity="wpm",
        kind=DependencyKind.BINARY_ARTIFACT,
        checkout_path=repo,
        expected_repository="https://example.invalid/real-repo.git",
        binary_relative_path="target/release/wpm",
    )
    admission = admit_dependency(decl)
    assert admission.outcome is DependencyOutcome.ADMITTED_DEPENDENCY
    import hashlib

    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert any(f"sha256={digest}" in d for d in admission.detail)


# --------------------------------------------------------------------------
# The real machine, right now
# --------------------------------------------------------------------------


def test_real_level4_dependencies_admit_to_typed_outcomes_only() -> None:
    admissions = admit_level4_dependencies()
    assert len(admissions) == 4
    for adm in admissions:
        assert isinstance(adm.outcome, DependencyOutcome)
        if adm.outcome is DependencyOutcome.ADMITTED_DEPENDENCY:
            assert adm.recorded_revision is not None
        if adm.outcome is DependencyOutcome.UNKNOWN_DEPENDENCY_IDENTITY_UNPROVEN:
            assert adm.unproven_reasons != ()


def test_probe_checkout_reads_the_real_sibling_shas() -> None:
    """Directory-exists is not standing: the SHA is read, not assumed."""
    for path in (Path("/Users/sac/gymact"), Path("/Users/sac/wasm4pm-compat")):
        identity = probe_checkout(path)
        assert isinstance(identity, CheckoutIdentity)
        if not identity.path_exists:
            pytest.skip(f"{path} absent on this machine")
        assert identity.is_git_repository
        real = _run(path, "git", "rev-parse", "HEAD")
        assert identity.head_sha == real
