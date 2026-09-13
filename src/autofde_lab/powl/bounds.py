# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Termination bounds for bounded POWL 2.0 traversal.

These are *budget declarations only*. Nothing here actuates, admits, or
brokers; a bound simply says how much traversal a candidate-plan computation
is permitted to spend before it stops.
"""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.fabric.canonical import sha256 as _sha256

__all__ = ["ExecutionBound", "DEFAULT_BOUND"]


@dataclass(frozen=True, slots=True)
class ExecutionBound:
    """Hard ceilings on a bounded traversal."""

    max_activity_fires: int = 1024
    max_node_visits: int = 4096
    max_marking_states: int = 8192

    def sha256(self) -> str:
        """Content hash of this bound, via ``autofde_lab.fabric.canonical``."""
        return _sha256(
            {
                "max_activity_fires": self.max_activity_fires,
                "max_node_visits": self.max_node_visits,
                "max_marking_states": self.max_marking_states,
            }
        )


DEFAULT_BOUND = ExecutionBound()
