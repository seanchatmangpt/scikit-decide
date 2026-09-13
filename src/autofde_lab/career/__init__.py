# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Career Graph and post-LLM résumé generation utilities.

See `books/post-llm-career` (Appendix A: Career Graph Worksheet, Appendix G:
Post-LLM Résumé and Role-Brief Templates) for the methodology this module
implements as real, callable code.
"""

from autofde_lab.career.resume import (
    Capability,
    CareerGraph,
    Evidence,
    Outcome,
    Resume,
    generate_resume,
)

__all__ = [
    "CareerGraph",
    "Capability",
    "Evidence",
    "Outcome",
    "Resume",
    "generate_resume",
]
