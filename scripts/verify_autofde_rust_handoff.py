#!/usr/bin/env python3
"""Qualify the exact AutoFDE Lab -> ggen -> Rust AutoFDE handoff graph.

This verifier is deliberately non-actuating. It inspects exact source identities and
the consumer/manufacturer contracts, then emits a deterministic qualification receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import tomllib

SHA1 = re.compile(r"^[0-9a-f]{40}$")


class Refusal(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed in {root}: {result.stderr.strip()}")
    return result.stdout.strip()


def exact_head(root: Path, expected: str, label: str) -> str:
    if not SHA1.fullmatch(expected):
        raise Refusal(f"{label}: expected revision is not an exact git SHA-1")
    actual = git(root, "rev-parse", "HEAD")
    if actual != expected:
        raise Refusal(
            f"{label}: exact-head mismatch actual={actual} expected={expected}"
        )
    return actual


def require_tokens(path: Path, tokens: list[str], label: str) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise Refusal(f"{label}: missing contract tokens: {missing}")


def require_prose_tokens(path: Path, tokens: list[str], label: str) -> None:
    """Require prose tokens while ignoring Markdown line wrapping only."""
    text = " ".join(path.read_text(encoding="utf-8").split())
    missing = [token for token in tokens if " ".join(token.split()) not in text]
    if missing:
        raise Refusal(f"{label}: missing contract tokens: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path("ecosystem/autofde-rust-handoff.toml")
    )
    parser.add_argument("--lab", type=Path, default=Path("."))
    parser.add_argument("--ggen", type=Path, required=True)
    parser.add_argument("--autofde", type=Path, required=True)
    parser.add_argument("--gymact", type=Path, required=True)
    args = parser.parse_args()

    with args.manifest.open("rb") as handle:
        contract = tomllib.load(handle)

    if contract.get("schema") != "autofde-lab.rust-handoff/1":
        raise Refusal("manifest schema mismatch")
    if contract.get("release") != "26.8.19":
        raise Refusal("release identity mismatch")
    if contract.get("authority") != "SELECT_ONLY":
        raise Refusal("Lab handoff must remain SELECT_ONLY")
    if contract.get("crown_requires_exact_execution") is not True:
        raise Refusal("source manifest may not self-crown")

    source = contract["source"]
    manufacturer = contract["manufacturer"]
    consumer = contract["consumer"]
    gymact = contract["gymact"]
    qualification = contract["qualification"]

    if source["repository"] != "seanchatmangpt/autofde-lab":
        raise Refusal("unexpected Lab repository")
    lab_head = git(args.lab, "rev-parse", "HEAD")
    if not SHA1.fullmatch(lab_head):
        raise Refusal("Lab HEAD is not an exact git SHA-1")
    base = source["base_revision"]
    if not SHA1.fullmatch(base):
        raise Refusal("Lab base revision is not exact")
    ancestor = subprocess.run(
        ["git", "-C", str(args.lab), "merge-base", "--is-ancestor", base, lab_head],
        check=False,
        text=True,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise Refusal(f"Lab HEAD {lab_head} does not descend from admitted base {base}")

    checks: dict[str, str] = {
        "lab_exact_head_descends_from_base": "ALIVE",
    }

    require_prose_tokens(
        args.lab / "CLAUDE.md",
        [
            "It computes candidate plans. It does not actuate.",
            "A planner selects; a broker authorizes; an executor performs; a verifier evaluates.",
        ],
        "Lab SELECT-only doctrine",
    )
    checks["lab_select_only"] = "ALIVE"

    require_tokens(
        args.lab / source["interop_ontology"],
        [
            "afl:InteropContract",
            "afl:ExternalRepresentation",
            "afl:InteropContractReceipt",
            "afl:semanticsPreserved",
        ],
        "Lab interop ontology",
    )
    checks["lab_interop_contract_present"] = "ALIVE"

    ggen_head = exact_head(args.ggen, manufacturer["revision"], "ggen")
    checks["ggen_exact_revision"] = "ALIVE"

    if manufacturer["request_schema"] != "autofde.manufacture-request/1":
        raise Refusal("manufacture request schema drift")
    if manufacturer["receipt_schema"] != "autofde.manufacture-receipt/2":
        raise Refusal("manufacture receipt schema drift")
    if manufacturer["validator"] != "ggen:autofde-capability-bundle/2":
        raise Refusal("manufacture validator drift")
    if (
        manufacturer["authority_mode"] != "external-only"
        or manufacturer["do_authority"] is not False
    ):
        raise Refusal("handoff attempted to smuggle DO authority")

    autofde_head = exact_head(args.autofde, consumer["revision"], "autofde")
    checks["autofde_exact_revision"] = "ALIVE"

    manufacturing_py = args.autofde / "src/autofde/manufacturing.py"
    require_tokens(
        manufacturing_py,
        [
            'schema: str = "autofde.manufacture-request/1"',
            'MANUFACTURE_RECEIPT_SCHEMA = "autofde.manufacture-receipt/2"',
            'MANUFACTURE_VALIDATOR = "ggen:autofde-capability-bundle/2"',
            'authority_mode: str = "external-only"',
            "do_authority: bool = False",
            "MANUFACTURE_REQUEST_MUST_BE_CONSTRUCT_ONLY",
            '"lab_revision": self.lab_revision',
            '"revision": self.ggen_revision',
        ],
        "AutoFDE manufacture request",
    )
    checks["manufacture_request_schema"] = "ALIVE"
    checks["construct_only_authority"] = "ALIVE"

    runtime_rs = args.autofde / "src/runtime.rs"
    require_tokens(
        runtime_rs,
        [
            f'pub const BUNDLE_SCHEMA: &str = "{consumer["bundle_schema"]}"',
            f'pub const RUNTIME_ABI: &str = "{consumer["runtime_abi"]}"',
            "lab_revision",
            "ggen_revision",
            "bundle_digest",
        ],
        "AutoFDE Rust runtime",
    )
    checks["capability_bundle_schema"] = "ALIVE"
    checks["runtime_abi"] = "ALIVE"
    checks["revision_binding"] = "ALIVE"

    with (args.lab / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    lab_pin = pyproject["tool"]["uv"]["sources"]["gymact"]["rev"]
    if lab_pin != gymact["admitted_revision"]:
        raise Refusal(
            f"GymAct admitted pin moved without qualification: actual={lab_pin} "
            f"expected={gymact['admitted_revision']}"
        )
    checks["gymact_admitted_pin_unchanged"] = "ALIVE"

    gymact_head = exact_head(
        args.gymact, gymact["candidate_revision"], "gymact candidate"
    )
    checks["gymact_candidate_exact_revision"] = "ALIVE"

    required = qualification["required_checks"]
    if sorted(required) != sorted(checks):
        raise Refusal(
            f"qualification check set drift: manifest={sorted(required)} executed={sorted(checks)}"
        )

    receipt: dict[str, Any] = {
        "schema": qualification["receipt_schema"],
        "release": contract["release"],
        "standing": qualification["success_standing"],
        "authority": {
            "lab": "SELECT_ONLY",
            "manufacturer": manufacturer["authority_mode"],
            "do_authority": False,
        },
        "subject": {
            "lab_repository": source["repository"],
            "lab_revision": lab_head,
            "lab_base_revision": base,
            "ggen_repository": manufacturer["repository"],
            "ggen_revision": ggen_head,
            "autofde_repository": consumer["repository"],
            "autofde_revision": autofde_head,
            "gymact_repository": gymact["repository"],
            "gymact_admitted_revision": gymact["admitted_revision"],
            "gymact_candidate_revision": gymact_head,
        },
        "contracts": {
            "manufacture_request_schema": manufacturer["request_schema"],
            "manufacture_receipt_schema": manufacturer["receipt_schema"],
            "manufacture_validator": manufacturer["validator"],
            "capability_bundle_schema": consumer["bundle_schema"],
            "runtime_abi": consumer["runtime_abi"],
        },
        "checks": checks,
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
