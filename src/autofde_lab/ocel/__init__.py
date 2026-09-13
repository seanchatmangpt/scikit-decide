# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""OCEL 2.0 object-centric event logs -- a standard occurrence-log format.

Dependency-free (stdlib plus :mod:`autofde_lab.fabric.canonical`). Shapes
transcribed from ``~/wasm4pm-compat/src/ocel.rs`` (dual MIT / Apache-2.0);
see the per-module docstrings for the exact line ranges.

This package *describes* occurrences. It does not execute anything, and
emitting an OCEL log is not evidence that a workflow ran.

Typical executor use::

    log = (
        OcelLog()
        .with_objects(OcelObject("case-1", "WorkflowCase"))
        .append_event("e1", "Select Frame", [("case-1", "belongs_to")], timestamp_ns=1_000)
        .validate()
    )
    document = log.to_ocel2_json()
"""

from autofde_lab.ocel.log import (
    STATIC_ATTRIBUTE_NS,
    TIME_STABLE_OBJECT_ATTRIBUTES,
    OcelLog,
)
from autofde_lab.ocel.model import (
    OCEL,
    EventObjectLink,
    OCELEvent,
    OCELEventAttribute,
    OCELObject,
    OCELObjectAttribute,
    OCELRelationship,
    OCELType,
    OCELTypeAttribute,
    ObjectChange,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
    OcelValueKind,
    format_ns,
    parse_ns,
)
from autofde_lab.ocel.refusals import OcelError, OcelRefusal

__all__ = [
    "OcelLog",
    "STATIC_ATTRIBUTE_NS",
    "TIME_STABLE_OBJECT_ATTRIBUTES",
    "OcelRefusal",
    "OcelError",
    "OcelObject",
    "OcelEvent",
    "OcelAttribute",
    "OcelAttributeValue",
    "OcelValueKind",
    "EventObjectLink",
    "ObjectObjectLink",
    "ObjectChange",
    "OCEL",
    "OCELType",
    "OCELTypeAttribute",
    "OCELEvent",
    "OCELObject",
    "OCELRelationship",
    "OCELEventAttribute",
    "OCELObjectAttribute",
    "format_ns",
    "parse_ns",
]
