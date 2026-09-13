# Executable Design Science

## Research by Construction, Falsification, Receipt, and Replay

**Sean Chatman**
Independent Researcher

### Abstract

Design Science Research established that knowledge about computational systems can be produced through the construction and evaluation of artifacts. Research Through Design similarly treats artifact construction as a mode of inquiry, while empirical systems research and artifact-evaluation programs increasingly require software, data, and experimental procedures to accompany published claims. Yet a persistent gap remains between an artifact that exists, an artifact that executes, evidence that an execution occurred, and evidence that the execution actually supports the scientific claim for which it was constructed.

This paper proposes **Executable Design Science (EDS)**, a research methodology in which executable computational artifacts, falsifiers, exact execution identities, receipts, process evidence, verification procedures, and independent reproduction form a single scientific object. EDS strengthens artifact-oriented research by requiring explicit separation among implementation, execution, observation, verification, and standing. Its central rule is:

$$
\text{implemented}
\neq
\text{executed}
\neq
\text{observed}
\neq
\text{verified}
\neq
\text{reproduced}.
$$

EDS emerged through a longitudinal software-research program conducted between August 1 and September 12, 2026. During this period, a collection of systems for ontology-driven software manufacture, executable simulated worlds, planning, process intelligence, authority-bounded actuation, receipts, and replay progressively converged around an explicit research lifecycle:

$$
ontology
\rightarrow
world
\rightarrow
infer
\rightarrow
plan
\rightarrow
falsify
\rightarrow
admit
\rightarrow
manufacture
\rightarrow
execute
\rightarrow
verify.
$$

The program subsequently incorporated hierarchical and nondeterministic planning, partial-order process models, object-centric event evidence, conformance checking, and Planning–Process Closure eXchange (PPCX). The implementation history exposed a recurring methodological problem: conventional labels such as "implemented," "working," "passing," or "successful" routinely collapsed materially different epistemic states.

EDS converts that engineering observation into a research method.

The paper contributes: a formal definition of an **Executable Research Claim**; an evidence-state model for computational claims; receipt-bound experimental identity; process-aware research evaluation using object-centric event data and conformance; a distinction between artifact correctness and scientific standing; an intelligence-amortization hypothesis in which validated recurring knowledge should reduce future general-purpose reasoning; and a falsifiable research agenda for evaluating EDS against conventional artifact-centric Design Science Research.

---

# 1. Introduction

A large class of computer-science research makes claims about things that can execute.

A paper may claim that an algorithm is faster, a planner covers more states, an architecture survives failure, a compiler preserves semantics, a workflow admits greater concurrency, a verification method rejects invalid behavior, or an autonomous system reacts correctly to environmental change.

Such claims are unusual compared with claims in many observational sciences because the subject of study is frequently **constructible**.

Researchers can create the mechanism about which the claim is being made.

This observation underlies Design Science Research. Hevner, March, Park, and Ram characterize design science as a research paradigm in which knowledge and understanding are developed through the building and application of artifacts.  Peffers, Tuunanen, Rothenberger, and Chatterjee subsequently provided a methodology progressing through problem identification, objectives, design and development, demonstration, evaluation, and communication.  Research Through Design similarly treats constructed artifacts as vehicles for research contributions rather than as implementation work occurring only after theory.

Modern computer science has moved still further toward artifact-oriented evaluation. ACM's artifact-review framework distinguishes the availability of research artifacts, whether artifacts have been independently evaluated, and whether results have been independently validated. Functional artifact evaluation specifically asks whether artifacts are documented, complete, exercisable, and supplied with appropriate verification and validation evidence.

These developments are substantial.

They nevertheless leave an important methodological gap.

Consider the following propositions:

$$
P_1:
\text{the source code exists}
$$

$$
P_2:
\text{the source code compiles}
$$

$$
P_3:
\text{the experiment executed}
$$

$$
P_4:
\text{the expected output was observed}
$$

$$
P_5:
\text{the output establishes the claimed scientific property}
$$

$$
P_6:
\text{another investigator can obtain equivalent evidence}.
$$

These propositions are not equivalent.

Yet computational research often permits evidence for one to drift rhetorically into another.

A repository may be cited as proof of a system.

A passing unit test may be cited as proof of external behavior.

An API acknowledgement may be cited as proof of physical consequence.

A benchmark may execute successfully while silently implementing a weaker experiment than the paper describes.

Recent work on AI-driven scientific experimentation demonstrates exactly this danger. Yu et al. report that experimentally successful code can still fail to faithfully implement the scientific protocol or support the intended research claim, and argue that execution alone is insufficient evidence of scientific success.

Executable Design Science begins from this distinction.

Its thesis is:

> **For research claims about executable systems, the scientific object should include not only the theory and artifact but also the exact executable claim, its falsifier, execution identity, resulting evidence, verification semantics, and reproduction path.**

The artifact is therefore neither supplementary material nor automatically scientific proof.

It is one stage in a larger epistemic process.

---

# 2. From Design Science to Executable Design Science

Design Science Research asks researchers to construct and evaluate artifacts capable of addressing important problems. Hevner et al. explicitly describe knowledge and understanding as emerging through building and application.

EDS accepts this foundation and adds a stricter computational condition:

$$
\boxed{
Artifact
\not\Rightarrow
Evidence
}
$$

and:

$$
\boxed{
Evidence
\not\Rightarrow
ClaimStanding
}
$$

without an explicit interpretation linking the observed evidence to the proposition being asserted.

The distinction is easiest to see in systems research.

Suppose a paper proposes a fault-tolerant deployment controller.

The implementation compiles.

That establishes something about its source and build environment.

The controller then executes a deployment.

That establishes that some program ran.

A remote service returns HTTP 200.

That establishes that the service acknowledged a request according to some interface semantics.

None of these observations independently establish:

> the desired external state transition occurred correctly and the proposed fault-tolerance property held.

EDS therefore extends the conventional DSR sequence:

$$
Problem
\rightarrow
Objectives
\rightarrow
Design
\rightarrow
Demonstration
\rightarrow
Evaluation
\rightarrow
Communication
$$

into:

$$
Problem
\rightarrow
Hypothesis
\rightarrow
ExecutableClaim
\rightarrow
Artifact
\rightarrow
Falsifier
\rightarrow
Execution
\rightarrow
Receipt
\rightarrow
Evidence
\rightarrow
Verification
\rightarrow
Reproduction
\rightarrow
Knowledge.
$$

The added stages are not intended as bureaucratic overhead.

They prevent distinct epistemic claims from becoming indistinguishable.

---

# 3. Origin of EDS as an Implementation-Derived Method

EDS did not begin as a retrospective renaming of Design Science Research.

It emerged from a software-research program in which implementation repeatedly exposed failures of ordinary research vocabulary.

The formative period considered in this paper spans August 1 through September 12, 2026.

The research program involved several interacting systems, including AutoFDE, AutoFDE-Lab, GymAct, ggen, ggen-marketplace, wasm4pm, Ash-based semantic systems, Reactor-based orchestration, process-intelligence infrastructure, and later explicit hierarchical and nondeterministic planning components.

The design direction was already explicit by August 11:

$$
\boxed{
ontology
\rightarrow
world
\rightarrow
infer
\rightarrow
plan
\rightarrow
falsify
\rightarrow
admit
\rightarrow
manufacture
\rightarrow
execute
\rightarrow
verify
}
$$

The intended division of responsibility was equally important.

AutoFDE-Lab owned expensive novelty and reasoning.

GymAct owned executable worlds and consequences.

ggen owned deterministic manufacture.

wasm4pm operated over process evidence.

The production path was not intended to continue reasoning indefinitely. Known solutions were to be compiled into reusable machinery.

This produced an early doctrine:

> **Production does not think. Production executes admitted thought.**

This statement became a precursor to the EDS intelligence-amortization hypothesis developed later in this paper.

---

# 4. The Formative Design History

The 43-day design history is not presented as a controlled experiment.

It is a formative longitudinal case from which methodological requirements were derived.

Its importance lies in repeated encounters with epistemic boundaries.

## 4.1 Early August: executable reality rather than architectural prose

The initial architecture separated exploratory reasoning from production execution.

GymAct increasingly became an executable-world and consequence layer rather than merely a benchmark harness. AutoFDE-Lab generated and falsified candidate solutions. ggen manufactured admitted solutions. Process evidence and replay became first-class outputs.

The central emerging requirement was:

$$
UNKNOWN
$$

must remain representable.

When execution could not establish the relevant state, the system was expected to refuse rather than convert missing evidence into optimistic inference.

This gave EDS its first principle:

$$
\boxed{
absence\ of\ falsification
\neq
verification.
}
$$

## 4.2 August 11: EDS becomes explicit

By August 11, the convergence target was already described as Executable Design Science.

The architecture was expected to connect ontology, executable worlds, inference, planning, falsification, admission, deterministic manufacture, execution, and verification.

This is important historically because it reverses the apparent causal order.

EDS did not arise because PPCX later suggested a research methodology.

Rather:

$$
EDS
\rightarrow
implementation
\rightarrow
planning/process\ formalization
\rightarrow
PPCX.
$$

PPCX eventually became a particularly clear demonstration of EDS.

It was not EDS's origin.

## 4.3 August 14–15: exact-subject standing

The implementation program increasingly rejected statements such as:

> the repository passes.

A repository is not a sufficiently precise experimental subject.

Instead, verification began to bind claims to exact source identities, dependency states, generated artifacts, and execution environments.

This produced states such as:

$$
ALIVE
$$

$$
PARTIAL\_ALIVE
$$

$$
BUILD\_BROKEN
$$

$$
BLOCKED
$$

$$
UNSUPPORTED.
$$

These states were deliberately not synonyms.

An AutoFDE evidence-bounded planning loop, for example, executed an exact-head test court rather than treating implementation existence as verification.

GymAct moved protocol semantics into admitted ontology rather than allowing an implementation to silently define them.

AutoFDE made planner authority explicit: choosing an action and possessing permission to execute it became separate concepts.

This period generated the EDS principle:

$$
\boxed{
subject\ identity
\ is\ part\ of\ evidence.
}
$$

## 4.4 August 16: observation, admission, manufacture, receipt

The Chatman Equation was formalized as:

$$
\boxed{
A=\mu(O^*)
}
$$

with:

$$
\boxed{
R=receipt(A).
}
$$

Here \(O\) represents available observations, while \(O^*\) denotes observations admitted as sufficiently aligned, grounded, and bounded for the transformation being attempted.

\(\mu\) represents lawful manufacture.

\(A\) represents the resulting artifact or candidate action.

The associated receipt \(R\) binds the resulting claim to an identity and evidentiary scope.

A critical distinction emerged:

$$
O
\neq
O^*.
$$

Available information does not automatically become scientific input.

Likewise:

$$
A
\neq
verified(A).
$$

An artifact's existence does not establish its consequence.

EDS later generalizes this equation from software manufacture to research claims.

## 4.5 August 19: executable constitutional infrastructure

By August 19, several architectural principles had moved from prose into executable systems.

A Rust consequence kernel implemented reversible option preservation, selection, construction, explicit authority, receipt reservation, actuation, observation, reconciliation, outcome classification, and non-actuating replay.

Tests enforced properties including:

$$
SELECT\neq CONSTRUCT\neq DO.
$$

Unknown states refused rather than guessing.

Acknowledgement was separated from completion.

Ambiguous outcomes did not automatically trigger blind retry.

Replay could inspect past execution without silently actuating again.

This period directly motivates the EDS requirement that a research workflow distinguish:

$$
proposal,
implementation,
execution,
observation,
verification.
$$

## 4.6 August 22: undecidability as an epistemic fence

Rice's theorem became a useful architectural fence.

Nontrivial semantic properties of arbitrary programs cannot in general be decided universally.

The methodological implication was not that verification is impossible.

It was that systems should avoid pretending bounded evidence proves arbitrary semantic properties.

EDS inherits this attitude.

Scientific claims must explicitly define their scope.

A test demonstrating property \(P\) for exact artifact \(a\) under environment \(e\) should not silently become:

$$
\forall x,\ P(x).
$$

Receipts establish bounded standing.

They do not provide metaphysical certainty.

## 4.7 August 23–29: scale exposes the difference between activity and evidence

Late August involved extensive implementation across many repositories and workstreams.

This period produced a particularly important negative lesson.

Large numbers of commits could be manufactured while scientific standing remained unchanged.

Some workstreams generated dozens of independently meaningful changes while whole-system execution remained unobserved.

Some exact semantic queries passed while broader runtime claims remained explicitly withheld.

Other workstreams reached a precise dependency or binary-transfer blocker and correctly retained:

$$
0
$$

qualifying consumer results despite substantial implementation effort.

This distinction became foundational:

$$
\boxed{
activity
\neq
evidence.
}
$$

and:

$$
\boxed{
commit\ volume
\neq
scientific\ standing.
}
$$

The correct EDS response to an exact blocker is not rhetorical completion.

It is a more precise state.

## 4.8 September 1: post-LLM knowledge consolidation

The September 1 architecture described a post-LLM condition in which solved problems progressively cease being runtime reasoning problems.

A recurring solution should become one or more of:

$$
ontology,
policy,
process\ law,
generator,
validator,
compiled\ transition\ geometry.
$$

The implementation loop increasingly resembled:

$$
observation
\rightarrow
semantic\ interpretation
\rightarrow
manufacture
\rightarrow
governed\ publication
\rightarrow
external\ consequence
\rightarrow
receipt
\rightarrow
process\ evidence.
$$

This produced the EDS intelligence principle:

> **Successful research should reduce how much general intelligence an equivalent future problem requires.**

Research knowledge that cannot be operationalized may remain useful.

But for known computational transformations, repeated rediscovery represents incomplete consolidation.

## 4.9 September 9–11: semantics, planning, process, and temporal evidence

The architecture subsequently connected ontology-driven relational/RDF mappings, Ash semantics, capability resolution, planning, Reactor coordination, authority-bounded execution, provenance, and OCEL-style event evidence.

FOND supplied nondeterministic policy semantics.

HDDL supplied hierarchical task structure.

POWL supplied process structure.

GitVan/KGC-4D work explored native temporal and causal receipt semantics.

Knowledge-hook work attempted to observe state-changing actions and evaluate them through explicit semantic surfaces rather than hidden callbacks.

Several implementations remained only PARTIAL_ALIVE or BUILD_BLOCKED.

Those states are methodologically important.

EDS requires negative execution evidence to remain visible.

## 4.10 September 12: PPCX reveals the general closure

By September 12 the planning/process relationship became explicit.

HDDL describes admissible hierarchical accomplishment.

FOND describes policy under fully observable nondeterministic outcomes.

POWL 2.0 describes partial-order process geometry.

OCEL records object-centric process evidence.

Conformance relates expected and observed execution.

Authority remains separate from planner recommendation.

The resulting loop was named:

**Planning–Process Closure eXchange (PPCX)**.

Conceptually:

$$
O_t^*
\xrightarrow{\mathcal P}
\Pi_t
\xrightarrow{\mathcal A}
A_t
\xrightarrow{\mathcal X}
E_{t+1}
\xrightarrow{\mathcal I}
O_{t+1}^*.
$$

PPCX exposed that the same structure existed at the research-method level:

$$
Theory
\rightarrow
Artifact
\rightarrow
Experiment
\rightarrow
Evidence
\rightarrow
Knowledge
\rightarrow
Theory'.
$$

This made EDS's general form visible.

---

# 5. Related Research

## 5.1 Design Science Research

EDS is most directly an extension of Design Science Research.

Hevner et al. define design science around the creation and application of artifacts and provide guidelines for producing rigorous and relevant design-science work.

Peffers et al. provide an explicit methodological sequence for conducting DSR and evaluating its products.

EDS does not replace these methodologies.

It specializes them for executable computational claims.

Its additional question is:

> What exact execution evidence must exist before the constructed artifact supports the scientific proposition being asserted?

## 5.2 Research Through Design

Zimmerman, Forlizzi, and Evenson describe Research Through Design as a method through which novel artifacts embody research integrations and move the world from current toward preferred states.

EDS shares the proposition that making can be inquiry.

Its additional emphasis is evidence-bearing execution.

For EDS:

$$
making
$$

is necessary for some claims but:

$$
making
\neq
knowing
$$

until the relevant behavior has been exercised and evaluated.

## 5.3 Artifact evaluation and reproducibility

ACM artifact-review programs already treat software and other research products as first-class objects of independent evaluation. ACM currently distinguishes artifact availability, artifact evaluation, and results validation.  Conferences implementing these guidelines ask evaluators to exercise submitted systems and determine whether artifacts support paper claims.

EDS can be understood partly as moving these concerns **upstream**.

Instead of treating reproducibility as a publication-stage package, EDS makes reproducibility constraints part of artifact architecture and experiment design from the beginning.

## 5.4 Process mining and process science

Process mining provides another major foundation.

Van der Aalst distinguishes process discovery, conformance checking, enhancement, and operational support as central uses of event data.

The Process Mining Manifesto similarly positions process mining as a mechanism for improving the redesign, control, and support of operational processes.

EDS adopts a reflexive extension:

> Research is itself a process capable of generating analyzable event evidence.

Thus an experiment can be compared with its declared research protocol.

Scientific-method drift can become a conformance problem.

## 5.5 Automated planning and process intelligence

Planning and process mining already have important intersections.

de Leoni, Lanciano, and Marrella transformed partially ordered conformance-checking problems into automated-planning problems and evaluated the approach experimentally.

Fettke and Rombach explicitly argue that AI planning, machine learning, and process mining have historically developed separately and propose a framework for deriving process models from execution data, constructing planning problems, and adaptively planning future business-process execution.

Prescriptive process monitoring also attempts to use process observations to recommend interventions during running processes. Kubrak et al.'s systematic review identifies runtime intervention as an active research area while noting needs including stronger real-world validation and attention to causality and second-order effects.

EDS is broader than these intersections because the process being controlled may be **research itself**.

## 5.6 Hierarchical nondeterministic planning

HDDL supplies a common input representation for hierarchical planning.

Chen and Bercher formalized Flexible FOND HTN planning, explicitly combining hierarchical structure with uncertainty in action outcomes.

Yousefi and Bercher subsequently introduced the first approach for computing strong solutions to FOND-HTN problems, including grounding, search, heuristics, and benchmark problems.

EDS uses this work primarily in its experimental-orchestration and PPCX programs rather than claiming novelty in the planning formalism.

## 5.7 POWL 2.0

Kourani, Park, and van der Aalst introduced POWL 2.0 as an extension of partially ordered workflow modeling incorporating choice graphs for more expressive decision and cyclic structures while retaining formal process properties. Their 2026 evaluation uses 17 real-life event logs.

POWL is particularly relevant to EDS because scientific work is often partially ordered.

Independent validation need not always wait for documentation.

Dataset preparation need not always wait for implementation.

Total ordering can therefore inject constraints absent from the scientific method.

## 5.8 OCEL and object-centric evidence

OCEL 2.0 represents events involving multiple related objects and supports object relationships, changing object attributes, and qualified event-object relationships.

This is a natural representation for research experiments.

One experimental event may simultaneously concern:

$$
Hypothesis,
Artifact,
Commit,
Dataset,
Environment,
Solver,
Validator,
Receipt.
$$

Forcing such evidence into a single artificial case identifier can erase relationships important for scientific interpretation.

## 5.9 Emerging executable-research work

Very recent work suggests independent convergence toward some EDS concerns.

Le's 2026 cybersecurity-methodology review converts methodological families into executable protocols with ordered steps, instruments, evaluation criteria, validity threats, and reporting checklists.

Yu et al.'s ABE-Ralph work argues that successful execution is insufficient and that AI-driven experiments must be audited for fidelity to the scientific claim and reference protocol.

These works are strongly adjacent.

Neither, however, defines the complete EDS research object proposed here: claim, artifact, executable falsifier, exact execution identity, receipt, process evidence, verification semantics, and reproduction as one closed knowledge-production system.

---

# 6. The Executable Research Claim

The fundamental EDS unit is the **Executable Research Claim (ERC)**.

Define:

$$
ERC=
\langle
H,A,F,E,V
\rangle
$$

where:

\(H\) is a falsifiable hypothesis,

\(A\) is the executable artifact operationalizing the hypothesis,

\(F\) is at least one explicit falsifier,

\(E\) is execution evidence,

and \(V\) is a verification procedure mapping evidence to bounded claim standing.

This can be augmented operationally with:

$$
P
$$

for protocol,

$$
I
$$

for exact execution identity,

and:

$$
R
$$

for reproduction package.

Thus the operational research object becomes:

$$
ERC^+
=
\langle
H,A,F,P,I,E,V,R
\rangle.
$$

The distinction matters.

A hypothesis with no executable artifact remains legitimate research but is not yet an executable research claim.

An artifact with no falsifier is a demonstration.

An executed artifact with no evidentiary interpretation is an observation.

A result with no reproduction route remains dependent on the original investigator's environment.

---

# 7. Evidence States

EDS introduces explicit claim states.

Let:

$$
S\in
\{
PROPOSED,
IMPLEMENTED,
EXECUTABLE,
OBSERVED,
VERIFIED,
REPRODUCIBLE,
REPRODUCED,
FALSIFIED,
BLOCKED,
UNSUPPORTED,
UNKNOWN
\}.
$$

These should not be interpreted as a single simplistic maturity ladder.

Some are orthogonal.

For example, an artifact can be executable while the scientific claim remains unsupported.

A result can be reproducible within one environment but not independently reproduced.

A hypothesis can be falsified despite a completely functional artifact.

The key prohibition is state collapse:

$$
IMPLEMENTED\neq VERIFIED
$$

$$
EXECUTABLE\neq OBSERVED\_CONSEQUENCE
$$

$$
OBSERVED\neq VERIFIED
$$

$$
VERIFIED\neq INDEPENDENTLY\_REPRODUCED.
$$

EDS therefore treats epistemic classification as part of experimental output.

---

# 8. Receipts

An EDS execution should produce sufficient evidence to bind the scientific claim to the execution that allegedly supports it.

Let:

$$
\rho=
receipt(
H,
A,
source,
dependencies,
environment,
inputs,
execution,
outputs,
validators
).
$$

The receipt should allow a later observer to answer:

What exact hypothesis was being exercised?

What exact artifact was executed?

What source revision produced it?

What dependency state existed?

What environment existed?

What inputs were admitted?

What executable path occurred?

What output was observed?

Which validator interpreted it?

What proposition does that evidence support?

The receipt therefore carries **standing**.

It does not merely prove that a command ran.

This yields:

$$
\boxed{
named\ experiment
\neq
executed\ experiment.
}
$$

and:

$$
\boxed{
executed\ experiment
\neq
verified\ claim.
}
$$

---

# 9. Falsifiers as First-Class Artifacts

EDS requires every strong computational claim to identify what would weaken it.

Suppose:

$$
H:
Method_A
\text{ provides higher nondeterministic branch coverage than }
Method_B.
$$

A falsifier may be:

$$
Coverage(A)
\leq
Coverage(B)
$$

under a preregistered or otherwise fixed benchmark and measurement procedure.

The crucial property is not that a falsifier must occur.

It is that the research artifact makes contradictory evidence representable.

A system incapable of producing output contradicting its own thesis is not a strong scientific instrument.

Therefore:

$$
\boxed{
NoExecutableFalsifier
\Rightarrow
LimitedExecutableStanding.
}
$$

Negative runs must remain evidence.

They must not disappear into CI noise or be rewritten as narrative exceptions.

---

# 10. Research as a Process

EDS treats research itself as an operational process.

A simplified scientific workflow might contain:

$$
FormHypothesis
$$

$$
ConstructArtifact
$$

$$
ConstructBaseline
$$

$$
PrepareEnvironment
$$

$$
Execute
$$

$$
CollectEvidence
$$

$$
Validate
$$

$$
Analyze
$$

$$
Reproduce.
$$

Many relationships are partial rather than total.

For example, preparation of an independent validator can occur concurrently with implementation.

Documentation can proceed while benchmarks execute.

A baseline can sometimes be prepared before the experimental artifact is complete.

POWL-style partial-order modeling is therefore useful:

$$
A\prec D
$$

may be known while no relation exists between \(A\) and \(B\).

EDS follows:

$$
\boxed{
do\ not\ manufacture\ sequence
\ where\ only\ partial\ order\ is\ known.
}
$$

This is both an efficiency rule and an epistemic rule.

---

# 11. Object-Centric Research Evidence

Scientific processes involve multiple interacting objects.

An execution can concern:

* one hypothesis;
* several source revisions;
* one benchmark dataset;
* multiple generated artifacts;
* one or more execution environments;
* several validators;
* multiple measurements.

A case-centric log obscures these relationships.

EDS therefore proposes object-centric experimental logging.

Conceptually:

$$
Event:
ExperimentRun
$$

relates to:

$$
Hypothesis:H_7
$$

$$
Artifact:A_{12}
$$

$$
Commit:C_{42}
$$

$$
Dataset:D_3
$$

$$
Environment:E_8
$$

$$
Validator:V_4.
$$

OCEL 2.0 already provides a standards-based representation for this class of relationship.

This enables process mining over scientific work itself.

---

# 12. Conformance as Methodological Verification

Process conformance asks whether observed behavior fits a reference process model.

EDS applies the same concept to research protocols.

Suppose an experiment declares:

$$
LoadDataset
\rightarrow
TrainModel
\rightarrow
EvaluateFullTestSet.
$$

The actual event history reveals:

$$
LoadSubset
\rightarrow
UsePrecomputedOutput
\rightarrow
EvaluateSubset.
$$

The software may execute successfully.

The experimental process does not conform to the declared method.

This distinction is especially relevant to AI-generated scientific software, where methodological substitutions can occur while producing plausible outputs.

EDS therefore distinguishes:

$$
code\ correctness
$$

from:

$$
protocol\ conformance.
$$

Both can be necessary for scientific standing.

---

# 13. The Chatman Equation as an EDS Research Transformation

EDS generalizes the Chatman Equation:

$$
A=\mu(O^*).
$$

For research, let:

$$
O
$$

be available observations.

Admission produces:

$$
O^*\subseteq O
$$

containing the observations permitted to support the specific claim.

The research transformation:

$$
\mu
$$

constructs an artifact, hypothesis update, model, or experimental action.

The artifact then yields:

$$
A.
$$

Execution produces receipt:

$$
R=receipt(A).
$$

The scientific cycle becomes:

$$
O_t^*
\rightarrow
A_t
\rightarrow
R_t
\rightarrow
E_{t+1}
\rightarrow
O_{t+1}^*.
$$

The equation is therefore not limited to software manufacture.

It describes an evidence-bounded transformation from admitted knowledge into an artifact whose consequence generates the next knowledge state.

---

# 14. HDIT and Information Preservation

The author's HDIT framework supplies an information-preservation interpretation of EDS.

Every research transformation can destroy information:

$$
Theory
\rightarrow
Formalization
\rightarrow
Implementation
\rightarrow
Experiment
\rightarrow
Measurement
\rightarrow
Publication.
$$

The key question becomes:

> Which distinctions must survive each projection for the downstream scientific conclusion to remain valid?

Suppose two experimental states:

$$
s_1
$$

and:

$$
s_2
$$

require different scientific interpretations:

$$
V(s_1)\neq V(s_2).
$$

If a measurement projection \(f\) maps them to:

$$
f(s_1)=f(s_2),
$$

then the projection has destroyed decision-relevant information.

The problem may be invisible if only the final measurement is inspected.

EDS therefore requires researchers to identify **information-preservation obligations**, not only software correctness obligations.

---

# 15. Intelligence Amortization

One of the strongest hypotheses to emerge from the implementation program is that successful computational research should eventually make some recurring reasoning unnecessary.

Suppose a novel problem initially requires expensive human or machine reasoning:

$$
G_0.
$$

Research discovers a stable mapping.

That mapping becomes:

$$
rule,
ontology,
solver,
generator,
validator,
policy,
process.
$$

For an equivalent future case, required general-purpose reasoning should decline.

Let:

$$
G
$$

be general reasoning required and:

$$
K_v
$$

be accumulated verified operational knowledge.

EDS proposes the hypothesis:

$$
\boxed{
\frac{\partial G}
{\partial K_v}<0
}
$$

for recurring problem classes.

This does not mean intelligence becomes unnecessary in general.

The frontier moves.

Previously solved transformations become infrastructure.

Novelty remains outside the compiled boundary.

This produces:

$$
UNKNOWN
\rightarrow
Explore
\rightarrow
Formalize
\rightarrow
Verify
\rightarrow
Automate
\rightarrow
Reuse.
$$

The empirical question is whether this transformation actually reduces future reasoning cost without degrading correctness.

That is testable.

---

# 16. PPCX as a Flagship EDS Experiment

Planning–Process Closure eXchange is a strong candidate for the first flagship EDS program.

PPCX connects prescriptive planning with descriptive process intelligence:

$$
O_t^*
\xrightarrow{\mathcal P}
\Pi_t
\xrightarrow{\mathcal A}
A_t
\xrightarrow{\mathcal X}
E_{t+1}
\xrightarrow{\mathcal I}
O_{t+1}^*.
$$

Its components draw heavily on established research.

HDDL provides hierarchical task structure.

FOND-HTN provides hierarchical strategy under nondeterministic outcomes.

POWL 2.0 provides partial-order process structure.

OCEL provides object-centric execution evidence.

Process mining provides discovery and conformance.

The research question is not whether each component works independently.

The EDS question is whether the **closure itself** can be made executable and falsifiable.

One PPCX ERC might be:

$$
H_1:
$$

A system that feeds verified conformance deviations back into its planning model will encounter fewer previously observed unhandled execution states than a system that logs deviations but does not update its planning model.

The artifact implements both conditions.

The falsifier is:

$$
Unhandled_{PPCX}
\geq
Unhandled_{Control}
$$

after controlled re-exposure to previously discovered deviations.

The experiment generates receipts and OCEL evidence.

The verification procedure calculates whether the difference exists.

The reproduction package permits another group to repeat the experiment.

This is EDS in concrete form.

---

# 17. Research Questions

The initial EDS research program should answer six questions.

### RQ1

Can computational research claims be represented as executable research claims connecting hypothesis, artifact, falsifier, execution evidence, and verifier?

### RQ2

Does exact execution identity and receipt binding reduce ambiguity between implementation evidence and scientific evidence?

### RQ3

Can process-conformance methods detect deviations between declared research protocols and actual experimental execution?

### RQ4

Does object-centric experimental logging improve the reconstruction and auditability of complex computational experiments?

### RQ5

Can verified recurring reasoning be compiled into deterministic artifacts without reducing correctness or relevant semantic coverage?

### RQ6

Does such consolidation measurably reduce the amount of general-purpose reasoning required for equivalent future problem instances?

---

# 18. Evaluation Framework

EDS itself requires evaluation.

It should not be defended solely by constructing an EDS-compliant demonstration.

A comparative study can assign equivalent computational research problems to two conditions:

$$
C_{DSR}
$$

using conventional artifact-oriented design-science practice, and:

$$
C_{EDS}
$$

using executable claims, receipts, explicit falsifiers, process evidence, and reproduction automation.

Potential dependent measures include:

$$
ClaimEvidenceMismatch
$$

the number of claims not directly supported by the artifact evidence cited for them;

$$
ProtocolDeviationDetection
$$

the fraction of injected experimental deviations correctly detected;

$$
ReproductionSuccess
$$

the fraction of results independently obtained;

$$
TimeToFalsification
$$

the time required to discover that a claim fails under a predeclared countercondition;

$$
EnvironmentAmbiguity
$$

the number of executions for which exact subject or environment cannot be reconstructed;

and:

$$
ReasoningReuse
$$

the reduction in general-purpose reasoning required for repeated equivalent tasks after knowledge has been formalized.

EDS succeeds only if these improvements justify its additional machinery.

---

# 19. Falsifiers of EDS

EDS must expose conditions under which its own methodology should be rejected or narrowed.

### F1 — Receipts do not improve scientific traceability

If conventional experiment metadata permits equivalent reconstruction and verification at lower cost, receipt machinery is unnecessary.

### F2 — Process modeling adds bureaucracy without detecting meaningful methodological deviations

If process evidence does not identify failures missed by ordinary experiment automation, the process-intelligence component should be removed.

### F3 — Explicit epistemic states do not reduce overclaiming

If researchers using EDS collapse execution and verification at the same rate as conventional workflows, the state model provides little practical benefit.

### F4 — Reproduction outcomes do not improve

If EDS packages are no easier to reproduce independently than well-prepared conventional artifacts, EDS has failed one of its principal goals.

### F5 — Intelligence does not amortize

If formalized verified knowledge fails to reduce subsequent reasoning requirements, the intelligence-amortization hypothesis is false for the tested domain.

### F6 — EDS costs exceed its epistemic value

If maintaining receipts, process models, validators, and research provenance costs more than the errors they prevent or knowledge they preserve, lighter methodologies may be preferable.

These falsifiers are central.

Without them, EDS would violate its own doctrine.

---

# 20. Threats to Validity

The formative case described in this paper comes from a single researcher and an interconnected family of software projects.

It is therefore unsuitable for causal claims about the superiority of EDS.

The August–September history should be interpreted as **requirements discovery through longitudinal implementation**, not controlled validation.

A second threat is instrumentation reflexivity.

Systems designed around receipts and evidence naturally produce more evidence artifacts than systems not designed that way. Quantity alone therefore cannot demonstrate epistemic superiority.

A third threat is overformalization.

Some scientific insights arise through exploratory work that should not be prematurely constrained by rigid executable protocols.

EDS should therefore be strongest after a research question becomes sufficiently concrete to admit falsifiable computational claims.

A fourth threat concerns independence.

An author executing an author's validator over an author's artifact is useful but not independent reproduction.

EDS must preserve that distinction explicitly.

A fifth threat is domain limitation.

The methodology is most directly applicable to computational research whose claims can be operationalized through executable artifacts.

It should not be generalized automatically to all forms of scientific inquiry.

---

# 21. Research Artifacts and Data

A mature EDS publication should provide enough information to traverse:

$$
Claim
\rightarrow
Artifact
\rightarrow
Experiment
\rightarrow
Evidence
\rightarrow
Result.
$$

At minimum this includes exact source identity, dependency state, executable experiment entrypoint, benchmark or input identity, explicit falsifier, raw outputs, validation procedure, machine-readable receipt, and scripts or workflows capable of regenerating reported quantitative results.

This requirement is consistent with the trajectory of ACM artifact evaluation but moves artifact discipline from publication packaging into research architecture.

The private design-conversation corpus used to reconstruct EDS's formative history is not necessary to reproduce the technical claims of the methodology.

Public technical claims should ultimately be reconstructable from executable research artifacts and archived evidence.

This is itself an EDS principle:

> private deliberation may explain provenance, but public scientific standing should not depend on inaccessible reasoning history.

---

# 22. Discussion

EDS changes the unit of computational research.

In conventional publication practice, the paper is often treated as the canonical research object and artifacts as supporting evidence.

EDS reverses this hierarchy.

The canonical object becomes a graph connecting:

$$
Claim
$$

$$
Artifact
$$

$$
Execution
$$

$$
Evidence
$$

$$
Verification
$$

$$
Reproduction.
$$

The paper becomes one human-readable projection of that graph.

This does not diminish scientific writing.

Interpretation, motivation, prior art, abstraction, and theory remain indispensable.

But prose should not possess more standing about an executable property than the evidence-producing system underneath it.

The resulting architecture is strikingly similar to PPCX.

PPCX closes:

$$
Planning
\rightarrow
Execution
\rightarrow
ProcessEvidence
\rightarrow
Planning'.
$$

EDS closes:

$$
Theory
\rightarrow
Artifact
\rightarrow
Experiment
\rightarrow
Evidence
\rightarrow
Theory'.
$$

Both systems treat consequence as information.

Both refuse to equate intention with reality.

Both use observation to alter what can lawfully happen next.

---

# 23. A Stronger Meaning of "Research by Implementation"

The phrase "research by implementation" can suggest that writing code itself produces scientific novelty.

EDS rejects that weak interpretation.

Implementation is useful because construction can reveal constraints that remain invisible in prose.

But EDS requires the stronger chain:

$$
construction
\rightarrow
exposure\ to\ falsification
\rightarrow
observation
\rightarrow
verification
\rightarrow
knowledge.
$$

A failed implementation may therefore generate more scientific value than a successful demonstration.

A dependency contradiction may invalidate an assumption.

A nondeterministic outcome may reveal a missing state transition.

A conformance deviation may show that the experimental protocol was not actually performed.

An independent reproducer may discover an environmental dependency hidden from the original researcher.

EDS treats all of these as outputs.

Research is not the production of green indicators.

It is the reduction of uncertainty through disciplined contact with falsifiable reality.

---

# 24. The EDS Principle of Knowledge Consolidation

The implementation history behind EDS repeatedly converged on one principle:

$$
\boxed{
Meaning\ once
\rightarrow
use\ everywhere
\rightarrow
reason\ less.
}
$$

This should be interpreted carefully.

It does not imply that all scientific reasoning can be eliminated.

It means that stable transformations discovered through research should become reusable structure when possible.

A discovered invariant can become a validator.

A recurring semantic mapping can become ontology.

A repeated planning decision can become policy.

A repeated software pattern can become a generator.

A repeated experimental procedure can become executable protocol.

A known falsifier can become a test.

Scientific knowledge therefore accumulates not only as text but as **operational capability**.

This is the characteristic EDS extension to ordinary design science.

---

# 25. Conclusion

Executable Design Science proposes that computational research can become substantially more precise when claims, artifacts, executions, evidence, verification, and reproduction are treated as distinct but connected scientific objects.

EDS builds directly upon Design Science Research, Research Through Design, process science, automated planning, empirical systems research, and reproducible-computing practice.

Its novelty claim should therefore remain narrow.

EDS does not claim that artifact construction is new.

It does not claim that executable research artifacts are new.

It does not claim that reproducibility is new.

It does not claim that process mining, automated planning, provenance, or formal verification are new.

Its proposed contribution is their methodological closure:

$$
\boxed{
Claim
\rightarrow
Artifact
\rightarrow
Falsifier
\rightarrow
Execution
\rightarrow
Receipt
\rightarrow
Evidence
\rightarrow
Verification
\rightarrow
Reproduction
\rightarrow
Knowledge.
}
$$

The formative implementation history from August 1 through September 12, 2026 demonstrates why this closure became necessary.

Repeatedly, the work encountered states where:

the code existed but did not execute;

the executable existed but the consumer was blocked;

a bounded semantic check passed but whole-system standing remained unknown;

an action was selected but lacked authority;

a request was acknowledged but its consequence had not been established;

an experimental path failed but the failure itself produced useful evidence.

The methodology was derived from preserving those distinctions.

Its core invariants are therefore:

$$
\boxed{
Implemented\neq Executed
}
$$

$$
\boxed{
Executed\neq Verified
}
$$

$$
\boxed{
SELECT\neq DO
}
$$

$$
\boxed{
Activity\neq Evidence
}
$$

$$
\boxed{
Evidence\neq Standing
}
$$

and:

$$
\boxed{
Repetition\ of\ solved\ reasoning
\ should\ become\ structure.
}
$$

The most ambitious EDS hypothesis is consequently not that machines will perform more research.

It is that valid research should make some future research operations **less dependent on rediscovery**.

If a scientific result is computationally stable, recurring, and sufficiently formalizable, then the result should eventually exist not only as prose but as executable knowledge.

Under EDS, the final question posed to a computational paper is therefore no longer only:

> Is the argument convincing?

Nor only:

> Is the code available?

It becomes:

> **Can the claim be executed, contradicted, receipted, inspected, and independently reproduced—and does what survives that process become reusable knowledge?**

That is **Executable Design Science**.

---

# References

Berti, A., Koren, I., Adams, J. N., Park, G., Knopp, B., Graves, N., Rafiei, M., Liß, L., Tacke Genannt Unterberg, L., Zhang, Y., Schwanen, C., Pegoraro, M., & van der Aalst, W. M. P. (2024). *OCEL (Object-Centric Event Log) 2.0 Specification.*

Chen, D. Z., & Bercher, P. (2022). *Flexible FOND HTN Planning: A Complexity Analysis.* Proceedings of the International Conference on Automated Planning and Scheduling, 32(1), 26–34. doi:10.1609/icaps.v32i1.19782.

de Leoni, M., Lanciano, G., & Marrella, A. (2018). *Aligning Partially-Ordered Process-Execution Traces and Models Using Automated Planning.* Proceedings of the International Conference on Automated Planning and Scheduling, 28(1), 321–329. doi:10.1609/icaps.v28i1.13911.

Fettke, P., & Rombach, A. (2022). *Towards Automated Process Planning and Mining.* arXiv:2208.08943.

Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). *Design Science in Information Systems Research.* MIS Quarterly, 28(1).

Höller, D., Behnke, G., Bercher, P., Biundo, S., Fiorino, H., Pellier, D., & Alford, R. (2020). *HDDL: An Extension to PDDL for Expressing Hierarchical Planning Problems.* Proceedings of the AAAI Conference on Artificial Intelligence, 34(06), 9883–9891. doi:10.1609/aaai.v34i06.6542.

Kourani, H., Park, G., & van der Aalst, W. M. P. (2026). *A discovery technique for expressive yet sound process models.* Process Science, 3, 14. doi:10.1007/s44311-026-00046-8.

Kubrak, K., Milani, F., Nolte, A., & Dumas, M. (2022). *Prescriptive process monitoring: Quo vadis?* PeerJ Computer Science, 8, e1097. doi:10.7717/peerj-cs.1097.

Peffers, K., Tuunanen, T., Rothenberger, M. A., & Chatterjee, S. (2007). *A Design Science Research Methodology for Information Systems Research.* Journal of Management Information Systems, 24(3), 45–77. doi:10.2753/MIS0742-1222240302.

van der Aalst, W. M. P. (2016). *Process Mining: Data Science in Action.* Springer.

Yousefi, M., & Bercher, P. (2024). *Laying the Foundations for Solving FOND HTN Problems: Grounding, Search, Heuristics (and Benchmark Problems).* Proceedings of IJCAI 2024, 6796–6804. doi:10.24963/ijcai.2024/751.

Yu, L., Xu, X., Zhou, Y., He, S., & Pan, A. (2026). *Beyond Execution: Auditing Experimental Fidelity in LLM-Driven Scientific Research.* arXiv:2608.26753.

Zimmerman, J., Forlizzi, J., & Evenson, S. (2007). *Research Through Design as a Method for Interaction Design Research in HCI.* Proceedings of CHI 2007. doi:10.1145/1240624.1240704.

---

**Editorial note on positioning (from the author, 2026-09-12):** This version is deliberately positioned as the foundational EDS paper, not yet the empirical validation paper. The next manuscript should be much narrower: select 3–5 ERCs from the existing implementation history, package exact artifacts and receipts, then experimentally compare EDS against a conventional artifact-evaluation workflow. That second paper is where the methodology becomes its own falsifiable subject.
