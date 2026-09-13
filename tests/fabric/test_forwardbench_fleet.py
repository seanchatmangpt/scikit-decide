from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autofde_lab.fabric.forwardbench_fleet import (
    audit_forwardbench_fleet,
    materialize_forwardbench_fleet,
)
from autofde_lab.fabric.vendor_materialization import VendorMaterializationState


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def init_repo(path: Path, label: str) -> str:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "AutoFDE Test")
    git(path, "config", "user.email", "autofde@example.invalid")
    (path / "subject.txt").write_text(label)
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "initial")
    return git(path, "rev-parse", "HEAD")


def make_fleet(tmp_path: Path):
    parent = tmp_path / "parent"
    init_repo(parent, "parent")
    pins = {}
    for slug in ("alpha", "beta"):
        source = tmp_path / f"source-{slug}"
        pins[slug] = init_repo(source, slug)
        git(
            parent,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(source),
            f"vendor/gyms/{slug}",
        )
        git(
            parent,
            "config",
            "-f",
            ".gitmodules",
            f"submodule.{slug}.update",
            "none",
        )
    git(parent, "add", ".gitmodules")
    git(parent, "commit", "-q", "-m", "pin fleet")
    lock = "@prefix afb: <x#> .\n" + "\n".join(
        f'<https://x/data/forwardbench/vendor-{slug}> afb:pinnedRevision "{sha}" ; afb:resolutionStanding "PINNED" .'
        for slug, sha in sorted(pins.items())
    )
    return parent, pins, lock


def test_fleet_audit_requires_every_pinned_subject_exact(tmp_path):
    parent, _, lock = make_fleet(tmp_path)
    report = audit_forwardbench_fleet(parent, lock)
    assert report.total == 2
    assert report.materialized_exact == 2
    assert report.complete


def test_fleet_materializer_initializes_all_unmaterialized_exactly(tmp_path):
    parent, pins, lock = make_fleet(tmp_path)
    for slug in pins:
        git(parent, "submodule", "deinit", "-f", "--", f"vendor/gyms/{slug}")
    before = audit_forwardbench_fleet(parent, lock)
    assert before.materialized_exact == 0
    assert len(before.unmaterialized) == 2

    after = materialize_forwardbench_fleet(parent, lock, allow_file_protocol=True)
    assert after.complete
    assert {a.observed_revision for a in after.audits} == set(pins.values())


def test_fleet_never_overwrites_populated_parent_inheriting_vendor(tmp_path):
    parent, _, lock = make_fleet(tmp_path)
    rogue = parent / "vendor/gyms/alpha"
    subprocess.run(["rm", "-rf", str(rogue)], check=True)
    rogue.mkdir()
    (rogue / "keep").write_text("rogue")

    report = materialize_forwardbench_fleet(parent, lock, allow_file_protocol=True)
    alpha = next(a for a in report.audits if a.path.endswith("alpha"))
    assert alpha.state is VendorMaterializationState.REFUSED_PARENT_INHERITANCE
    assert (rogue / "keep").read_text() == "rogue"
    assert not report.complete


def test_unknown_requested_slug_is_refused_before_git_side_effect(tmp_path):
    parent, _, lock = make_fleet(tmp_path)
    with pytest.raises(KeyError):
        materialize_forwardbench_fleet(parent, lock, slugs=["not-pinned"])
