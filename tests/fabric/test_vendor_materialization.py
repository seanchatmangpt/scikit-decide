from __future__ import annotations

import subprocess
from pathlib import Path

from autofde_lab.fabric.vendor_materialization import (
    VendorMaterializationState,
    audit_vendor,
    gitlink_revision,
    parse_gym_lock,
)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def init_repo(path: Path, name: str) -> str:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "AutoFDE Test")
    git(path, "config", "user.email", "autofde@example.invalid")
    (path / "subject.txt").write_text(name)
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "initial")
    return git(path, "rev-parse", "HEAD")


def make_superproject(tmp_path: Path):
    source = tmp_path / "source"
    source_sha = init_repo(source, "vendor")
    parent = tmp_path / "parent"
    init_repo(parent, "parent")
    (parent / "vendor" / "gyms").mkdir(parents=True)
    git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(source),
        "vendor/gyms/example",
    )
    git(parent, "commit", "-q", "-am", "pin vendor")
    return parent, source, source_sha


def test_lock_parser_extracts_pins():
    text = """@prefix afb: <x#> .\n<https://x/data/forwardbench/vendor-example> afb:pinnedRevision "0123456789abcdef0123456789abcdef01234567" ; afb:resolutionStanding "PINNED" ."""
    assert parse_gym_lock(text) == {
        "example": "0123456789abcdef0123456789abcdef01234567"
    }


def test_materialized_submodule_owns_identity_and_matches_pin(tmp_path):
    parent, _, sha = make_superproject(tmp_path)
    audit = audit_vendor(parent, "vendor/gyms/example", pinned_revision=sha)
    assert audit.state is VendorMaterializationState.MATERIALIZED_EXACT
    assert audit.observed_revision == sha
    assert audit.observed_root == str((parent / "vendor/gyms/example").resolve())


def test_empty_uninitialized_gitlink_does_not_inherit_parent_identity(tmp_path):
    parent, _, sha = make_superproject(tmp_path)
    vendor = parent / "vendor/gyms/example"
    subprocess.run(["rm", "-rf", str(vendor)], check=True)
    vendor.mkdir()
    audit = audit_vendor(parent, "vendor/gyms/example", pinned_revision=sha)
    assert audit.state is VendorMaterializationState.PINNED_UNMATERIALIZED
    assert audit.observed_revision is None


def test_populated_plain_directory_is_refused_for_parent_inheritance(tmp_path):
    parent, _, sha = make_superproject(tmp_path)
    vendor = parent / "vendor/gyms/example"
    subprocess.run(["rm", "-rf", str(vendor)], check=True)
    vendor.mkdir()
    (vendor / "not-a-checkout.txt").write_text("rogue")
    audit = audit_vendor(parent, "vendor/gyms/example", pinned_revision=sha)
    assert audit.state is VendorMaterializationState.REFUSED_PARENT_INHERITANCE
    assert audit.observed_revision is None


def test_materialized_revision_drift_is_refused(tmp_path):
    parent, source, sha = make_superproject(tmp_path)
    (source / "subject.txt").write_text("new")
    git(source, "commit", "-q", "-am", "new source head")
    new_sha = git(source, "rev-parse", "HEAD")
    vendor = parent / "vendor/gyms/example"
    git(vendor, "fetch", "-q", str(source), new_sha)
    git(vendor, "checkout", "-q", new_sha)
    audit = audit_vendor(parent, "vendor/gyms/example", pinned_revision=sha)
    assert audit.state is VendorMaterializationState.REFUSED_REVISION_MISMATCH
    assert audit.observed_revision == new_sha
    assert audit.gitlink_revision == sha


def test_semantic_pin_must_equal_gitlink_before_worktree_is_trusted(tmp_path):
    parent, _, _ = make_superproject(tmp_path)
    wrong = "f" * 40
    audit = audit_vendor(parent, "vendor/gyms/example", pinned_revision=wrong)
    assert audit.state is VendorMaterializationState.REFUSED_PIN_MISMATCH


def test_ordinary_directory_cannot_be_a_vendor_subject(tmp_path):
    parent = tmp_path / "parent"
    init_repo(parent, "parent")
    path = parent / "vendor/gyms/example"
    path.mkdir(parents=True)
    (path / "x").write_text("x")
    audit = audit_vendor(parent, "vendor/gyms/example")
    assert audit.state is VendorMaterializationState.REFUSED_NOT_GITLINK
    assert gitlink_revision(parent, "vendor/gyms/example") is None
