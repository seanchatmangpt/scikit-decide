"""Real OCEL 2.0 JSON export of a GymAct episode's `Receipt` trail.

This is the fix for "claims must be checkable, not narrated": a standing
claim like "GymAct actuated subject X" should be re-derivable by an
independent party from a real, schema-conformant, content-addressed log --
not trusted from prose in a lock file. `receipts_to_ocel` builds that log
directly from real `Receipt`s already returned by `gymact.runtime.GymAct`
(no parallel/duplicate event representation); `validate_ocel_log` checks it
against the real official OCEL 2.0 JSON Schema (vendored at
`gymact/schemas/ocel20-schema.json`, fetched from
https://www.ocel-standard.org/2.0/ocel20-schema-json.json); `write_ocel_log`
persists it and returns its real sha256 digest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

from gymact.models import Receipt

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "ocel20-schema.json"


def _load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text())


def receipts_to_ocel(receipts: list[Receipt]) -> dict[str, Any]:
    """Build a real OCEL 2.0 log from one episode's real receipt trail.

    Object types: `episode` (the case-like object every event relates to),
    `environment` (from `subject_ref`), `capability` (from `capability_ref`,
    when present). Event types: one per distinct `Operation` value observed.
    Every field on the resulting events/objects is copied from real `Receipt`
    data -- nothing here is synthesized or inferred.
    """
    if not receipts:
        raise ValueError("cannot build an OCEL log from an empty receipt list")

    episode_ids: set[str] = set()
    environment_ids: set[str] = set()
    capability_ids: set[str] = set()
    event_type_names: set[str] = set()

    events: list[dict[str, Any]] = []
    for receipt in receipts:
        episode_ids.add(receipt.episode_id)
        if receipt.subject_ref:
            environment_ids.add(receipt.subject_ref)
        if receipt.capability_ref:
            capability_ids.add(receipt.capability_ref)
        event_type_names.add(receipt.operation.value)

        attributes = [
            {"name": "standing", "value": receipt.standing.value},
        ]
        for name, value in (
            ("reason", receipt.reason),
            ("authority_ref", receipt.authority_ref),
            ("authority_evidence_ref", receipt.authority_evidence_ref),
            ("idempotency_key", receipt.idempotency_key),
            ("pre_state_digest", receipt.pre_state_digest),
            ("post_state_digest", receipt.post_state_digest),
            ("verification_id", receipt.verification_id),
            ("error_digest", receipt.error_digest),
        ):
            if value is not None:
                attributes.append({"name": name, "value": value})

        relationships = [{"objectId": receipt.episode_id, "qualifier": "episode"}]
        if receipt.subject_ref:
            relationships.append({"objectId": receipt.subject_ref, "qualifier": "environment"})
        if receipt.capability_ref:
            relationships.append({"objectId": receipt.capability_ref, "qualifier": "capability"})

        events.append(
            {
                "id": receipt.receipt_id,
                "type": receipt.operation.value,
                "time": receipt.occurred_at,
                "attributes": attributes,
                "relationships": relationships,
            }
        )

    objects: list[dict[str, Any]] = []
    objects.extend({"id": eid, "type": "episode", "attributes": []} for eid in sorted(episode_ids))
    objects.extend(
        {"id": eid, "type": "environment", "attributes": []} for eid in sorted(environment_ids)
    )
    objects.extend(
        {"id": cid, "type": "capability", "attributes": []} for cid in sorted(capability_ids)
    )

    object_types = [{"name": "episode", "attributes": []}]
    if environment_ids:
        object_types.append({"name": "environment", "attributes": []})
    if capability_ids:
        object_types.append({"name": "capability", "attributes": []})

    event_types = [
        {
            "name": name,
            "attributes": [{"name": "standing", "type": "string"}],
        }
        for name in sorted(event_type_names)
    ]

    return {
        "eventTypes": event_types,
        "objectTypes": object_types,
        "events": events,
        "objects": objects,
    }


def validate_ocel_log(log: dict[str, Any]) -> None:
    """Validate `log` against the real official OCEL 2.0 JSON Schema.

    Raises `jsonschema.exceptions.ValidationError` naming the exact violation
    on failure; returns nothing (does not silently swallow a bad log) on
    success.
    """
    jsonschema.validate(
        instance=log,
        schema=_load_schema(),
        format_checker=jsonschema.FormatChecker(),
    )


def digest_ocel_log(log: dict[str, Any]) -> str:
    """Real sha256 over the log's canonical JSON serialization."""
    canonical = json.dumps(log, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def write_ocel_log(path: Path, receipts: list[Receipt]) -> tuple[dict[str, Any], str]:
    """Build, validate, persist an episode's OCEL log; return (log, sha256 digest).

    Validation runs before the file is written -- an invalid log is never
    persisted or digested as if it were real evidence. The digest is computed
    over the *exact bytes written to disk* (canonical: sorted keys, compact
    separators) -- a caller must be able to independently confirm the digest
    by running `sha256sum <path>` directly against the file, not by
    re-serializing it a different way and hoping the bytes happen to match.
    A pretty-printed file whose digest is taken over a differently-formatted
    in-memory copy is not independently checkable; this was caught and fixed
    during this session precisely because it wasn't.
    """
    log = receipts_to_ocel(receipts)
    validate_ocel_log(log)
    canonical = json.dumps(log, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical)
    return log, digest
