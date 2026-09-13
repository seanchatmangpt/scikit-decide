# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

__all__ = [
    "Action",
    "AddExpression",
    "AlwaysFormula",
    "AlwaysWithinFormula",
    "AssignEffect",
    "AtEndEffect",
    "AtEndFormula",
    "AtMostOnceFormula",
    "AtStartEffect",
    "AtStartFormula",
    "AtTimeEffect",
    "Class",
    "ConditionalEffect",
    "ConjunctionEffect",
    "ConjunctionFormula",
    "DecreaseEffect",
    "DerivedPredicate",
    "DisjunctionEffect",
    "DisjunctionFormula",
    "DivExpression",
    "Domain",
    "DurationEffect",
    "DurationExpression",
    "DurationFormula",
    "DurativeAction",
    "Effect",
    "EqFormula",
    "EqualityFormula",
    "Event",
    "ExistentialEffect",
    "ExistentialFormula",
    "Expression",
    "Formula",
    "Function",
    "FunctionExpression",
    "GoalAchievedExpression",
    "GreaterEqFormula",
    "GreaterFormula",
    "HoldAfterFormula",
    "HoldDuringFormula",
    "ImplyFormula",
    "IncreaseEffect",
    "LessEqFormula",
    "LessFormula",
    "MaximizeExpression",
    "MinimizeExpression",
    "MinusExpression",
    "MulExpression",
    "NegationEffect",
    "NegationFormula",
    "Number",
    "NumericalExpression",
    "Object",
    "OverAllFormula",
    "PDDL",
    "PDDLReader",
    "Predicate",
    "PredicateEffect",
    "PredicateFormula",
    "Preference",
    "ProbabilisticEffect",
    "Problem",
    "Process",
    "Requirements",
    "RewardExpression",
    "ScaleDownEffect",
    "ScaleUpEffect",
    "SometimeAfterFormula",
    "SometimeBeforeFormula",
    "SometimeFormula",
    "SubExpression",
    "Term",
    "TimeExpression",
    "TotalCostExpression",
    "TotalTimeExpression",
    "Type",
    "UniversalEffect",
    "UniversalFormula",
    "Variable",
    "ViolationExpression",
    "WithinFormula",
]

try:
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_ as PDDL
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Action_ as Action
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AddExpression_ as AddExpression
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AlwaysFormula_ as AlwaysFormula
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_AlwaysWithinFormula_ as AlwaysWithinFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AssignEffect_ as AssignEffect
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AtEndEffect_ as AtEndEffect
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AtEndFormula_ as AtEndFormula
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_AtMostOnceFormula_ as AtMostOnceFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AtStartEffect_ as AtStartEffect
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_AtStartFormula_ as AtStartFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_AtTimeEffect_ as AtTimeEffect
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Class_ as Class
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ConditionalEffect_ as ConditionalEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ConjunctionEffect_ as ConjunctionEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ConjunctionFormula_ as ConjunctionFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DecreaseEffect_ as DecreaseEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DerivedPredicate_ as DerivedPredicate,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DisjunctionEffect_ as DisjunctionEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DisjunctionFormula_ as DisjunctionFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_DivExpression_ as DivExpression
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Domain_ as Domain
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DurationEffect_ as DurationEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DurationExpression_ as DurationExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DurationFormula_ as DurationFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_DurativeAction_ as DurativeAction,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Effect_ as Effect
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_EqFormula_ as EqFormula
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_EqualityFormula_ as EqualityFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Event_ as Event
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ExistentialEffect_ as ExistentialEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ExistentialFormula_ as ExistentialFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Expression_ as Expression
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Formula_ as Formula
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Function_ as Function
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_FunctionExpression_ as FunctionExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_GoalAchievedExpression_ as GoalAchievedExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_GreaterEqFormula_ as GreaterEqFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_GreaterFormula_ as GreaterFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_HoldAfterFormula_ as HoldAfterFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_HoldDuringFormula_ as HoldDuringFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_ImplyFormula_ as ImplyFormula
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_IncreaseEffect_ as IncreaseEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_LessEqFormula_ as LessEqFormula
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_LessFormula_ as LessFormula
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_MaximizeExpression_ as MaximizeExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_MinimizeExpression_ as MinimizeExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_MinusExpression_ as MinusExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_MulExpression_ as MulExpression
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_NegationEffect_ as NegationEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_NegationFormula_ as NegationFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Number_ as Number
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_NumericalExpression_ as NumericalExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Object_ as Object
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_OverAllFormula_ as OverAllFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Predicate_ as Predicate
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_PredicateEffect_ as PredicateEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_PredicateFormula_ as PredicateFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Preference_ as Preference
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ProbabilisticEffect_ as ProbabilisticEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Problem_ as Problem
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Process_ as Process
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Requirements_ as Requirements
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_RewardExpression_ as RewardExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ScaleDownEffect_ as ScaleDownEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_ScaleUpEffect_ as ScaleUpEffect
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_SometimeAfterFormula_ as SometimeAfterFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_SometimeBeforeFormula_ as SometimeBeforeFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_SometimeFormula_ as SometimeFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_SubExpression_ as SubExpression
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Term_ as Term
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_TimeExpression_ as TimeExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_TotalCostExpression_ as TotalCostExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_TotalTimeExpression_ as TotalTimeExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Type_ as Type
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_UniversalEffect_ as UniversalEffect,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_UniversalFormula_ as UniversalFormula,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_Variable_ as Variable
    from autofde_lab.hub.__autofde_lab_hub_cpp import (
        _PDDL_ViolationExpression_ as ViolationExpression,
    )
    from autofde_lab.hub.__autofde_lab_hub_cpp import _PDDL_WithinFormula_ as WithinFormula
except ImportError:
    print(
        'Scikit-decide C++ hub library not found. Please check it is installed in "autofde_lab/hub".'
    )
    raise


class PDDLReader:
    """Convenience wrapper around the C++ PDDL parser.

    # Parameters
    files: One or more PDDL file paths (domain and/or problem files).
    verbose: Activates parsing traces.
    """

    def __init__(self, *files: str, verbose: bool = False):
        self._pddl = PDDL()
        if files:
            self._pddl.load(list(files), verbose)

    def load(self, *files: str, verbose: bool = False):
        """Parse additional PDDL files into this reader."""
        self._pddl.load(list(files), verbose)

    @property
    def domains(self):
        """Return the list of parsed domains."""
        return self._pddl.get_domains()

    @property
    def problems(self):
        """Return the list of parsed problems."""
        return self._pddl.get_problems()
