# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Named refusals for OCEL 2.0 log admission.

Shapes transcribed (not copied) from ``~/wasm4pm-compat/src/ocel.rs``
lines 905-940 (``OcelRefusal`` and its ``Display`` impl). That crate is
dual-licensed MIT / Apache-2.0.

Every rejection carries a named refusal, never a bare string: a caller can
branch on ``OcelError.refusal`` without parsing prose. The ``.detail`` field
is human-facing only and is never part of the contract.

Refusals 6-8 come from Küsters & van der Aalst (2025), "OCPQ: Object-Centric
Process Querying & Constraints" (arXiv:2506.11541), Definition 2, pp. 5-6.

Refusals 3-5 come from Gianola et al. (2026), "Detecting Dynamic
Relationships in Object-Centric Event Logs" -- Assumption 3 (exactly one
reference object per event) and Assumption 5 (Locality Principle).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["OcelRefusal", "OcelError"]


class OcelRefusal(StrEnum):
    """The complete set of named OCEL admission refusals."""

    #: An event-to-object link references an object not present in the log.
    #: Extended beyond the Rust source to also cover a link naming an unknown
    #: event, an object-to-object link with an unknown endpoint, and an object
    #: change naming an unknown object -- all structurally the same defect.
    DANGLING_EVENT_OBJECT_LINK = "DanglingEventObjectLink"

    #: The log, or one of its events, has no event-to-object links at all.
    #: This is the object-centricity law: an event that touches no object is
    #: not an object-centric event.
    EMPTY_EVENT_OBJECT_LINKS = "EmptyEventObjectLinks"

    #: Gianola (2026) Assumption 3: an event must have a reference object.
    MISSING_REFERENCE_OBJECT = "MissingReferenceObject"

    #: Gianola (2026) Assumption 3: an event has more than one reference object.
    MULTIPLE_REFERENCE_OBJECTS = "MultipleReferenceObjects"

    #: Gianola (2026) Assumption 5 (Locality Principle): an event implicitly
    #: modifies the relationships of an object other than its reference object.
    VIOLATES_LOCALITY_PRINCIPLE = "ViolatesLocalityPrinciple"

    #: Küsters & van der Aalst (2025), OCPQ, Definition 2 (p. 6): for the
    #: time-stable attributes ``a in {objects, type}`` the assigned value must
    #: not change over time. An ``ObjectChange`` naming one of them is refused.
    TIME_STABLE_ATTRIBUTE_CHANGED = "TimeStableAttributeChanged"

    #: OCPQ Definition 2 (pp. 5-6): ``E`` and ``O`` are *sets*, and each event
    #: has exactly one event type, each object exactly one object type. Two
    #: declarations sharing an id would give that id two types.
    DUPLICATE_ENTITY_ID = "DuplicateEntityId"

    #: OCPQ Definition 2 (pp. 5-6): ``eaval_e(objects) subset U_qual x O`` and
    #: ``oaval_o(objects) subset U_qual x O`` -- object references are
    #: *qualified*. Raised only under ``validate(strict_qualifiers=True)``; see
    #: the divergence note on :meth:`autofde_lab.ocel.log.OcelLog.validate`.
    UNQUALIFIED_OBJECT_REFERENCE = "UnqualifiedObjectReference"


class OcelError(ValueError):
    """Raised when an OCEL log violates a named admission law.

    Attributes:
        refusal: the named :class:`OcelRefusal`, the branchable part.
        detail: a human-facing explanation, never contractual.
    """

    def __init__(self, refusal: OcelRefusal, detail: str = "") -> None:
        self.refusal = refusal
        self.detail = detail
        super().__init__(f"{refusal.value}: {detail}" if detail else refusal.value)
