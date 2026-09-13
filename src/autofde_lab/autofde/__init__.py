# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""AutoFDE: one admitted work graph, four generated artifacts.

Renders ``ontology/autofde-phase-graph.ttl``'s A-Box subject as
``phase-graph.powl.json``, ``project_management.auto.tfvars`` and
``github-project-plan.json``, and reconstructs the work graph back out of the
generated tfvars to check the round-trip law.

This package is a leaf of the dependency graph: it depends on
:mod:`autofde_lab.powl`, and nothing under ``autofde_lab/{powl,agent,ocel,fabric}``
may import it (enforced by ``tests/autofde/test_explore_boundary.py``), so it
can be extracted to its own repository without unpicking anything.

It renders text and compares structure. It does not actuate: no
``terraform apply`` is ever run against the GitHub provider.
"""

from __future__ import annotations

from autofde_lab.autofde.github_projection import (
    IssueProjection,
    project,
    render_issue_body,
    render_powl_json,
    render_project_plan_json,
    render_tfvars,
)
from autofde_lab.autofde.phase_graph import (
    AUTOFDE_PHASE_GRAPH,
    Phase,
    PhaseGraph,
    WorkItem,
    reduce_order,
    work_partial_order,
)
from autofde_lab.autofde.reconstruct import (
    ParsedTfvars,
    ReconstructedGraph,
    ReconstructedItem,
    parse_tfvars,
    reconstruct_work_graph,
)
from autofde_lab.autofde.refusals import AutoFdeError, AutoFdeRefusal

__all__ = [
    "AutoFdeRefusal",
    "AutoFdeError",
    "Phase",
    "WorkItem",
    "PhaseGraph",
    "AUTOFDE_PHASE_GRAPH",
    "work_partial_order",
    "reduce_order",
    "IssueProjection",
    "project",
    "render_issue_body",
    "render_tfvars",
    "render_project_plan_json",
    "render_powl_json",
    "ParsedTfvars",
    "ReconstructedItem",
    "ReconstructedGraph",
    "parse_tfvars",
    "reconstruct_work_graph",
]
