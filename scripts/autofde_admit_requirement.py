#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQ_SCHEMA = "autofde.engineering-requirement/1"
ADM_SCHEMA = "autofde.lab-admission/1"
POWL2 = "https://truex.io/ontology/powl2#"
MFWP = "urn:mfw:powl-trace:"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_requirement(req: dict) -> None:
    if req.get("schema") != REQ_SCHEMA:
        raise ValueError("REFUSED:UNSUPPORTED_REQUIREMENT_SCHEMA")
    if req.get("standing") != "BLOCKED:CAPABILITY_ABSENT":
        raise ValueError("REFUSED:REQUIREMENT_NOT_CAPABILITY_ABSENT")
    if req.get("authority_class") not in (None, "CONSTRUCT"):
        raise ValueError("REFUSED:REQUIREMENT_AUTHORITY_ESCALATION")
    for field in ("requirement_id", "observation_digest", "capability"):
        if not isinstance(req.get(field), str) or not req[field]:
            raise ValueError(f"REFUSED:REQUIREMENT_{field.upper()}_MISSING")


def render_powl(req: dict, base_iri: str) -> str:
    rid = req["requirement_id"]
    plan = f"{base_iri.rstrip('/')}/{rid}/plan"
    steps = [
        ("admit-requirement", req["capability"]),
        ("manufacture-capability-bundle", req["capability"]),
        ("independent-validate-bundle", req["capability"]),
        ("promote-bundle-digest", req["capability"]),
        ("resume-blocked-occurrence", req["capability"]),
    ]
    lines = [
        f"@prefix powl2: <{POWL2}> .",
        f"@prefix mfwp: <{MFWP}> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        f"<{plan}> a powl2:Model, powl2:PartialOrder ;",
        f"    prov:wasDerivedFrom <urn:autofde:engineering-requirement:{rid}> ;",
        '    mfwp:plannerRun "autofde-lab:self-manufacture" ;',
        '    mfwp:projection "total-order" ;',
    ]
    for i in range(len(steps)):
        lines.append(f"    powl2:hasChild <{plan}/binding-slot/{i}> ;")
    lines.append(f'    mfwp:activityCount "{len(steps)}"^^xsd:integer .')
    lines.append("")
    for i, (name, capability) in enumerate(steps):
        step = f"{plan}/step/{i}"
        lines.extend(
            [
                f"<{plan}/binding-slot/{i}> a powl2:ChildBinding ;",
                f'    powl2:childIndex "{i}"^^xsd:integer ;',
                f"    powl2:childModel <{step}> .",
                "",
                f"<{step}> a powl2:Leaf, powl2:ActivityLeaf ;",
                f'    powl2:activityLabel "{name}" ;',
                f"    mfwp:implementsAction <urn:autofde:action:{name}> ;",
                f'    mfwp:planOrdinal "{i}"^^xsd:integer ;',
                f'    mfwp:capability "{capability}" .',
                "",
            ]
        )
    for i in range(len(steps) - 1):
        lines.append(
            f"<{plan}/binding-slot/{i}> powl2:precedes <{plan}/binding-slot/{i + 1}> ."
        )
    lines.append("")
    return "\n".join(lines)


def admit(requirement: dict, lab_revision: str, base_iri: str) -> tuple[dict, str]:
    validate_requirement(requirement)
    if not lab_revision:
        raise ValueError("REFUSED:LAB_REVISION_MISSING")
    powl = render_powl(requirement, base_iri)
    powl_digest = "sha256:" + hashlib.sha256(powl.encode()).hexdigest()
    admission = {
        "schema": ADM_SCHEMA,
        "standing": "ALIVE",
        "authority_class": "CONSTRUCT",
        "do_authority": False,
        "requirement_id": requirement["requirement_id"],
        "requirement_digest": sha256_json(requirement),
        "observation_digest": requirement["observation_digest"],
        "capability": requirement["capability"],
        "lab_revision": lab_revision,
        "powl_schema": "POWL2",
        "powl_digest": powl_digest,
        "activity_count": 5,
    }
    admission["admission_digest"] = sha256_json(admission)
    return admission, powl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirement")
    parser.add_argument("--lab-revision", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--powl-out", required=True)
    parser.add_argument("--base-iri", default="urn:autofde:self-manufacture")
    args = parser.parse_args()
    req = json.loads(Path(args.requirement).read_text())
    try:
        admission, powl = admit(req, args.lab_revision, args.base_iri)
    except ValueError as exc:
        print(json.dumps({"standing": str(exc)}))
        return 2
    Path(args.out).write_text(json.dumps(admission, indent=2, sort_keys=True) + "\n")
    Path(args.powl_out).write_text(powl)
    print(
        json.dumps(
            {
                "standing": "ALIVE",
                "admission_digest": admission["admission_digest"],
                "powl_digest": admission["powl_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
