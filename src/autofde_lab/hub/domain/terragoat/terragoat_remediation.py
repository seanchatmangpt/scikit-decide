# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic planning domain over real TerraGoat misconfiguration findings.

TerraGoat (vendored at ``vendor/gyms/terragoat``) is Bridgecrew's "vulnerable by
design" Terraform repository: each resource block in its ``.tf`` files carries
inline ``# <misconfiguration>`` comments documenting a specific finding (e.g.
"bucket is not encrypted"). This domain parses those real comments out of a
real vendored Terraform file at construction time (no fabricated findings) and
models remediation as a deterministic planning problem:

* **state**: the frozenset of finding ids not yet remediated.
* **action**: remediate one specific, still-open finding.
* **transition**: deterministically removes that finding from the open set,
  cost 1 per remediation.
* **goal**: the empty set (every parsed finding remediated).

This is a real, if bounded, decision problem instantiated from real gym
content, not a synthetic stand-in for one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, Optional

from autofde_lab import D, DeterministicPlanningDomain, Space, Value
from autofde_lab.hub.space.gym import ListSpace

DEFAULT_TERRAFORM_FILE = (
    Path(__file__).resolve().parents[5]
    / "vendor"
    / "gyms"
    / "terragoat"
    / "terraform"
    / "aws"
    / "s3.tf"
)

_RESOURCE_RE = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')


@dataclass(frozen=True)
class Finding:
    """One parsed misconfiguration finding from a real TerraGoat resource block."""

    id: str
    resource: str
    description: str


def _parse_findings_from_text(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in _RESOURCE_RE.finditer(text):
        rtype, rname = match.groups()
        resource = f"{rtype}.{rname}"
        rest = text[match.end() : match.end() + 2000]
        per_resource_index = 0
        for line in rest.split("\n"):
            stripped = line.strip()
            if stripped == "":
                continue
            if not stripped.startswith("#"):
                break
            description = stripped.lstrip("#").strip()
            findings.append(
                Finding(
                    id=f"{resource}#{per_resource_index}",
                    resource=resource,
                    description=description,
                )
            )
            per_resource_index += 1
    return findings


def parse_findings(
    terraform_file: Path | list[Path], max_findings: Optional[int] = None
) -> list[Finding]:
    """Parse ``# <misconfiguration>`` comment lines immediately following each
    ``resource "type" "name" {`` block header in one or more real TerraGoat
    ``.tf`` files.

    # Parameters
    terraform_file: path to a real vendored TerraGoat Terraform file, or a
        list of such paths (e.g. every real ``.tf`` file in one cloud
        subdirectory such as ``terraform/alicloud``, whose resources are
        split across multiple files rather than one).
    max_findings: if given, cap the number of findings returned (keeps the
        resulting planning problem tractable for a bounded demo domain).

    # Returns
    list[Finding]: findings in file order (files processed in the order
        given), each with a unique id ``"<resource_type>.<resource_name>#<n>"``.
    """
    files = [terraform_file] if isinstance(terraform_file, Path) else list(terraform_file)
    findings: list[Finding] = []
    for f in files:
        findings.extend(_parse_findings_from_text(f.read_text()))
        if max_findings is not None and len(findings) >= max_findings:
            return findings[:max_findings]
    return findings


class State(NamedTuple):
    open_findings: frozenset[str]


class D_(
    DeterministicPlanningDomain,
):
    T_state = State
    T_observation = T_state
    T_event = str  # finding id being remediated
    T_value = float
    T_predicate = bool
    T_info = None


class TerraGoatRemediation(D_):
    """Plan a sequence of remediations that clears every parsed TerraGoat finding."""

    def __init__(
        self,
        terraform_file: Path | list[Path] = DEFAULT_TERRAFORM_FILE,
        max_findings: Optional[int] = 8,
    ) -> None:
        """
        # Parameters
        terraform_file: real TerraGoat ``.tf`` file (or list of files -- e.g.
            every real ``.tf`` file in one cloud subdirectory, whose
            resources are split across multiple files) to parse findings
            from. Defaults to ``vendor/gyms/terragoat/terraform/aws/s3.tf``.
        max_findings: cap on how many parsed findings form the goal set,
            keeping the search space small and tractable. ``None`` means no
            cap -- use every real finding parsed.
        """
        self.terraform_file = (
            Path(terraform_file)
            if isinstance(terraform_file, (str, Path))
            else [Path(f) for f in terraform_file]
        )
        self.findings: list[Finding] = parse_findings(
            self.terraform_file, max_findings=max_findings
        )
        if not self.findings:
            raise ValueError(
                f"No misconfiguration findings parsed from {self.terraform_file}; "
                "cannot build a remediation domain with an empty finding set."
            )
        self._finding_ids = frozenset(f.id for f in self.findings)
        self._by_id = {f.id: f for f in self.findings}

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        return State(open_findings=memory.open_findings - {action})

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=1.0)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(sorted(self._finding_ids))

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(sorted(memory.open_findings))

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace([State(open_findings=frozenset())])

    def _get_initial_state_(self) -> D.T_state:
        return State(open_findings=self._finding_ids)

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace(
            [State(open_findings=frozenset())]
        )  # only the reachable-goal shape matters here; search doesn't sample this

    def describe_finding(self, finding_id: str) -> Finding:
        """Look up the real parsed Finding (resource + description) behind an action id."""
        return self._by_id[finding_id]
