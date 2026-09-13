import subprocess
from pathlib import Path

from autofde_lab.fabric.vendor_materialization import (
    VendorMaterializationState,
    audit_vendor,
)
from autofde_lab.fabric.vendor_materializer import materialize_vendor


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


def test_materializer_initializes_exact_gitlink_without_weakening_pin(tmp_path):
    parent, _, sha = make_superproject(tmp_path)
    git(parent, "submodule", "deinit", "-f", "--", "vendor/gyms/example")
    audit_before = audit_vendor(parent, "vendor/gyms/example", pinned_revision=sha)
    assert audit_before.state is VendorMaterializationState.PINNED_UNMATERIALIZED

    audit_after = materialize_vendor(
        parent,
        "vendor/gyms/example",
        pinned_revision=sha,
        allow_file_protocol=True,
    )
    assert audit_after.state is VendorMaterializationState.MATERIALIZED_EXACT
    assert audit_after.observed_revision == sha


def test_materializer_refuses_populated_parent_inheriting_directory(tmp_path):
    parent, _, sha = make_superproject(tmp_path)
    vendor = parent / "vendor/gyms/example"
    subprocess.run(["rm", "-rf", str(vendor)], check=True)
    vendor.mkdir()
    (vendor / "rogue").write_text("do not overwrite")

    audit = materialize_vendor(parent, "vendor/gyms/example", pinned_revision=sha)
    assert audit.state is VendorMaterializationState.REFUSED_PARENT_INHERITANCE
    assert (vendor / "rogue").read_text() == "do not overwrite"
