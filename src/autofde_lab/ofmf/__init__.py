# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A vendored Knowledge Hook substrate — including its actuating half.

At the user's explicit direction (2026-08-07), this package vendors the
**whole** reference file ``~/dev/.spec-kit.bak/src/specify_cli/ofmf/ofmf_keystone.py``
verbatim, plus its full dependency closure
(``kgc_ofmf_utils.py``, ``ofmf/event_adapter.py``, ``ofmf/utils.py``) — not
just the non-actuating ``RDFDelta``/``DialectSuite.sparql_ask``/
``DialectSuite.sparql_construct_to_delta`` slice a prior pass in this repo
scoped the port down to.

**Documented exception to this package's own invariant** (see
``src/autofde_lab/CLAUDE.md``: "nothing here actuates"): :class:`ofmf_keystone.OFMFEngine`
writes files to disk and, via ``SpiffWorkflowAdapter.submit_workflow``,
drives a real BPMN workflow engine — a genuine executor side effect. It ships
in this repo because the whole file was vendored as instructed, but **nothing
in ``autofde_lab`` imports, registers, calls, or exposes ``OFMFEngine`` or
``SpiffWorkflowAdapter``** through this ``__init__``, the fabric CLI/MCP
surface, or any entry point. Treat anything reached only via
``autofde_lab.ofmf.ofmf_keystone.OFMFEngine`` as vendored-but-inert, not as
part of this repo's candidate-plan-only surface.

This top-level package re-exports only the confirmed non-actuating pieces.
"""

from autofde_lab.ofmf.ofmf_keystone import DialectSuite, RDFDelta

__all__ = [
    "RDFDelta",
    "DialectSuite",
]
