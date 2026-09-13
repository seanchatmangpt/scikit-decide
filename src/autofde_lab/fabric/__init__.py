# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Agent-facing decision fabric for scikit-decide.

The fabric keeps solver semantics in scikit-decide and projects one typed
service through CLI, MCP, A2A, DSPy, and a receipt-bound ERRC cache.
"""

from autofde_lab.fabric.cache import SQLiteERRCCache
from autofde_lab.fabric.models import (
    CacheStatus,
    DecisionCatalog,
    DecisionMatch,
    DecisionRefusal,
    DecisionRequest,
    DecisionResult,
    DecisionStanding,
    RefusalCode,
)
from autofde_lab.fabric.service import DecisionFabric

__all__ = [
    "CacheStatus",
    "DecisionCatalog",
    "DecisionFabric",
    "DecisionMatch",
    "DecisionRefusal",
    "DecisionRequest",
    "DecisionResult",
    "DecisionStanding",
    "RefusalCode",
    "SQLiteERRCCache",
]
