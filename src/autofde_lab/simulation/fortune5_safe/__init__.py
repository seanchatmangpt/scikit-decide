"""Fortune-5 SAFe digital twin with deterministic DfCM policy search.

The simulation advances a model only. Its receipts bind simulated inputs and consequences and
carry no admission or real-world actuation authority.
"""

from .dfcm import run_full_matrix
from .engine import replay, run_episode
from .model import (
    APS_SOURCE_SHA,
    AUTOFDE_BASE_SHA,
    EnterpriseTopology,
    ExperimentResult,
    Fortune5Config,
    PolicyVector,
    Scenario,
    ScenarioName,
    SimulationReceipt,
)
from .space import SCENARIOS, all_policies
from .topology import build_topology


def summary(config: Fortune5Config = Fortune5Config()) -> dict:
    topology = build_topology(config)
    return {
        "source": f"seanchatmangpt/agile-protocol-specification@{APS_SOURCE_SHA}",
        "target_base": f"seanchatmangpt/autofde-lab@{AUTOFDE_BASE_SHA}",
        "topology": dict(topology.counts),
        "annual_budget_usd": topology.annual_budget_usd,
        "policy_count": len(all_policies()),
        "scenario_count": len(SCENARIOS),
        "episode_count": len(all_policies()) * len(SCENARIOS),
        "topology_digest": topology.digest,
        "authority": "NON_ACTUATING_MODEL_ONLY",
    }


__all__ = [
    "APS_SOURCE_SHA",
    "AUTOFDE_BASE_SHA",
    "SCENARIOS",
    "EnterpriseTopology",
    "ExperimentResult",
    "Fortune5Config",
    "PolicyVector",
    "Scenario",
    "ScenarioName",
    "SimulationReceipt",
    "all_policies",
    "build_topology",
    "replay",
    "run_episode",
    "run_full_matrix",
    "summary",
]
