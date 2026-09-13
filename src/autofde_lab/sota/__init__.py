# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The SOTA-attack layer: a real, cited DecisionBasis vocabulary (Model x Planner x
ToolPolicy x RepairPolicy x VerificationPolicy x Budget) extracted from this repo's already-
proven real agent-driven benchmark attempts (`harbor`/`terminus-2`, `sregym`/`stratus`), so
today's hardcoded configuration becomes one addressable point in an architecture-search space
rather than the unexamined architecture itself.

See `decision_basis.py` for the vocabulary, `materialize_sregym.py`/`materialize_harbor.py`
for the real, cited D0 points and their invocation-builders.
"""
