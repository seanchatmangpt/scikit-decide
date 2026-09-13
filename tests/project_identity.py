# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Single source of truth for the project's outward identity.

Every test that asserts on the distribution name, Python namespace, or
entry-point registry must import these constants rather than embed its own
string. A rename that only updates some of the embedded strings produces a
half-renamed state that passes silently -- entry-point groups return an
empty collection for an unknown name rather than raising, so a stale group
string degrades to "zero domains, zero solvers" with no error anywhere.
That is the exact failure this module exists to make impossible to miss.
"""

from __future__ import annotations

DISTRIBUTION_NAME = "autofde-lab"
PYTHON_NAMESPACE = "autofde_lab"
LEGACY_DISTRIBUTION_NAME = "scikit-decide"
LEGACY_NAMESPACE = "skdecide"

DOMAIN_ENTRYPOINT_GROUP = "autofde_lab.domains"
SOLVER_ENTRYPOINT_GROUP = "autofde_lab.solvers"
LEGACY_DOMAIN_ENTRYPOINT_GROUP = "skdecide.domains"
LEGACY_SOLVER_ENTRYPOINT_GROUP = "skdecide.solvers"

# Verified counts, this session, against the live pyproject.toml registry.
# Zero or partial enumeration after a rename must fail loudly against these,
# not return an empty catalog that looks like a clean but capability-less
# system.
# 2026-08-08: domain count moved 26 -> 31 after registering 5 gym-derived
# domains (terragoat_remediation, k8s_goat_rbac_escalation,
# azuregoat_privesc, cloudgoat_iam_privesc, fix_git_recovery) as real
# autofde_lab.domains entry points; re-verify with
# `entry_points(group="autofde_lab.domains")` before citing this number.
EXPECTED_DOMAIN_COUNT = 31
EXPECTED_SOLVER_COUNT = 57

NATIVE_EXTENSION_NAME = "__autofde_lab_hub_cpp"
LEGACY_NATIVE_EXTENSION_NAME = "__skdecide_hub_cpp"

ONTOLOGY_FILENAME = "autofde-lab-capabilities.ttl"
LEGACY_ONTOLOGY_FILENAME = "skdecide-capabilities.ttl"
