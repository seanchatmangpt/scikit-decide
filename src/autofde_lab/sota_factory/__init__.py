"""AutoFDE Lab SOTA factory control plane.

The package represents benchmark targets, DecisionBasis architecture spaces,
experiment designs, score/frontier standing, and failure-driven learning. The
``SOTAFactory`` itself remains SELECT/LEARN only. The single-target and portfolio
autopilots may invoke an injected execution port; GymAct keeps DO behind BRCE.
"""

from .autopilot import AutopilotPolicy, AutopilotRound, AutopilotRun, SOTAAutopilot
from .compiler import CompiledExperimentSet, ExperimentCompiler
from .done import DefinitionOfDone, DefinitionOfDoneReport, ProofObligation
from .execution import (
    ExecutionProfileRefused,
    ExecutionProfileResolver,
    ExperimentExecutionPort,
    GgenExecutionProfileBundleResolver,
    GymActExecutionPort,
    GymActExecutionProfile,
)
from .factory import FactorySnapshot, SOTAFactory
from .learning import FailureRouter, LearningCompiler, LearningSignal
from .models import (
    ArchitecturePoint,
    BasisChoice,
    BenchmarkScore,
    BenchmarkTarget,
    BudgetPolicy,
    DecisionBasis,
    ExperimentBasis,
    ExperimentPlan,
    FailureCluster,
    FailureKind,
    FrontierStanding,
    OptimizationDirection,
    RepairLeverage,
    SelectionStrategy,
    TrialOutcome,
    TrialResult,
)
from .portfolio import PortfolioSnapshot, SOTAPortfolio
from .portfolio_autopilot import (
    PortfolioAutopilotPolicy,
    PortfolioAutopilotRound,
    PortfolioAutopilotRun,
    SOTAPortfolioAutopilot,
)
from .score import ScoreLaw
from .scoreboard import Scoreboard
from .space import CompatibilityRule, DecisionSpace, hamming_distance, pairwise_covering

__all__ = [
    "ArchitecturePoint",
    "AutopilotPolicy",
    "AutopilotRound",
    "AutopilotRun",
    "BasisChoice",
    "BenchmarkScore",
    "BenchmarkTarget",
    "BudgetPolicy",
    "CompatibilityRule",
    "CompiledExperimentSet",
    "DecisionBasis",
    "DecisionSpace",
    "DefinitionOfDone",
    "DefinitionOfDoneReport",
    "ExecutionProfileRefused",
    "ExecutionProfileResolver",
    "ExperimentBasis",
    "ExperimentCompiler",
    "ExperimentExecutionPort",
    "ExperimentPlan",
    "FactorySnapshot",
    "FailureCluster",
    "FailureKind",
    "FailureRouter",
    "FrontierStanding",
    "GgenExecutionProfileBundleResolver",
    "GymActExecutionPort",
    "GymActExecutionProfile",
    "LearningCompiler",
    "LearningSignal",
    "OptimizationDirection",
    "PortfolioAutopilotPolicy",
    "PortfolioAutopilotRound",
    "PortfolioAutopilotRun",
    "PortfolioSnapshot",
    "ProofObligation",
    "RepairLeverage",
    "SOTAAutopilot",
    "SOTAFactory",
    "SOTAPortfolio",
    "SOTAPortfolioAutopilot",
    "ScoreLaw",
    "Scoreboard",
    "SelectionStrategy",
    "TrialOutcome",
    "TrialResult",
    "hamming_distance",
    "pairwise_covering",
]
