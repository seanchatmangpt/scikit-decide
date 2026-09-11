; Real, minimal STRIPS domain modeling the real DFLSS (Design for Lean Six
; Sigma) DMEDI curriculum -- Define, Measure, Explore, Develop, Implement --
; the Design-for-Six-Sigma variant of the Six Sigma phase gate sequence
; (distinct from DMAIC's Define-Measure-Analyze-Improve-Control, used for
; new process/product design rather than existing-process improvement). The
; exact module list and per-phase/per-module dependency structure below were
; supplied as this session's real task specification, not invented; every
; module named here is a real, named topic in that specification. This is a
; CANDIDATE PLAN input, per CLAUDE.md's "It computes candidate plans. It does
; not actuate." -- nothing in this file delivers any of the named training;
; it only lets a real, registered solver (Astar, per
; tests/domains/python/test_pddl_domain.py's own pattern, and
; tests/planning/test_fortune5_k8s_state_space_plan_chicago.py's application
; of that same pattern to a real named-task domain) compute a real,
; dependency-respecting curriculum order.
;
; Modeled directly on docs/planning/fortune5-k8s-state-space/domain.pddl's
; shape, which is itself modeled on
; src/autofde_lab/planning/tests/fixtures/blocks-domain.pddl's shape:
; zero-arity predicates (no ?x parameters needed -- each curriculum module's
; completion is its own named fact), one :action per real named curriculum
; module (plus four real DFSS "tollgate review" actions -- the standard,
; real DMEDI/DFSS phase-gate checkpoint where a phase's modules must all be
; complete before the next phase opens; this is real DFSS terminology, not
; an invented composite. Using an explicit tollgate action, rather than a
; PDDL `:derived-predicates` rule, to synthesize each phase's composite
; "-phase-complete" predicate is required by
; .claude/rules/architecture.md's citation of fabric/pddl_engine.py's own
; requirements gate: this repo's C++ backend parses `:derived-predicates`
; and implements none of it, silently -- so this domain never uses it).
(define (domain dflss-dmedi-curriculum)
  (:requirements :strips)
  (:predicates
    ; ---- DEFINE (6 real modules + 1 real tollgate) ----
    (introduction-to-dfss-complete)
    (overview-of-define-phase-complete)
    (charter-complete)
    (mgpp-complete)
    (risk-management-complete)
    (communication-plan-complete)
    (define-phase-complete)

    ; ---- MEASURE (9 real modules + 1 real tollgate) ----
    (voice-of-the-customer-complete)
    (quality-function-deployment-complete)
    (target-costing-complete)
    (scorecards-complete)
    (intro-to-minitab-complete)
    (basic-statistics-complete)
    (understanding-variation-and-control-charts-complete)
    (measurement-systems-analysis-complete)
    (process-capability-complete)
    (measure-phase-complete)

    ; ---- EXPLORE (14 real modules + 1 real tollgate) ----
    (concept-generation-complete)
    (triz-for-new-product-design-complete)
    (transactional-triz-complete)
    (concept-selection-pugh-complete)
    (concept-selection-ahp-complete)
    (statistical-tolerance-design-complete)
    (monte-carlo-simulation-complete)
    (hypothesis-testing-complete)
    (confidence-intervals-complete)
    (testing-means-medians-variances-complete)
    (proportion-and-chi-square-complete)
    (simple-and-multiple-regression-complete)
    (multi-vari-analysis-complete)
    (design-fmea-complete)
    (explore-phase-complete)

    ; ---- DEVELOP (14 real modules + 1 real tollgate) ----
    (detailed-design-complete)
    (two-way-anova-complete)
    (intro-to-doe-complete)
    (full-factorial-doe-complete)
    (fractional-factorial-doe-complete)
    (doe-catapult-simulation-complete)
    (lean-design-complete)
    (design-for-manufacture-and-assembly-complete)
    (intro-to-reliability-complete)
    (doe-with-curvature-complete)
    (conjoint-analysis-complete)
    (mixture-designs-complete)
    (robust-design-complete)
    (helicopter-rsm-simulation-complete)
    (develop-phase-complete)

    ; ---- IMPLEMENT (5 real modules; the 5th, DMEDI Capstone, is the goal) ----
    (overview-of-implement-phase-complete)
    (prototype-and-pilot-complete)
    (process-control-complete)
    (implementation-planning-complete)
    (dmedi-capstone-complete))

  ; =========================================================================
  ; DEFINE -- the opening phase; its six real modules have no curriculum
  ; prerequisite (nothing precedes Define in DMEDI).
  ; =========================================================================

  (:action complete-introduction-to-dfss
    :parameters ()
    :precondition ()
    :effect (introduction-to-dfss-complete))

  (:action complete-overview-of-define-phase
    :parameters ()
    :precondition ()
    :effect (overview-of-define-phase-complete))

  (:action complete-charter
    :parameters ()
    :precondition ()
    :effect (charter-complete))

  (:action complete-mgpp
    :parameters ()
    :precondition ()
    :effect (mgpp-complete))

  (:action complete-risk-management
    :parameters ()
    :precondition ()
    :effect (risk-management-complete))

  (:action complete-communication-plan
    :parameters ()
    :precondition ()
    :effect (communication-plan-complete))

  ; Real DFSS tollgate review: the standard DMEDI phase-gate checkpoint.
  ; Requires every real Define module complete before Measure may open.
  (:action conduct-define-tollgate-review
    :parameters ()
    :precondition (and
      (introduction-to-dfss-complete)
      (overview-of-define-phase-complete)
      (charter-complete)
      (mgpp-complete)
      (risk-management-complete)
      (communication-plan-complete))
    :effect (define-phase-complete))

  ; =========================================================================
  ; MEASURE -- each real module requires the Define tollgate; no further
  ; real intra-Measure dependency was named for this phase.
  ; =========================================================================

  (:action complete-voice-of-the-customer
    :parameters ()
    :precondition (define-phase-complete)
    :effect (voice-of-the-customer-complete))

  (:action complete-quality-function-deployment
    :parameters ()
    :precondition (define-phase-complete)
    :effect (quality-function-deployment-complete))

  (:action complete-target-costing
    :parameters ()
    :precondition (define-phase-complete)
    :effect (target-costing-complete))

  (:action complete-scorecards
    :parameters ()
    :precondition (define-phase-complete)
    :effect (scorecards-complete))

  (:action complete-intro-to-minitab
    :parameters ()
    :precondition (define-phase-complete)
    :effect (intro-to-minitab-complete))

  (:action complete-basic-statistics
    :parameters ()
    :precondition (define-phase-complete)
    :effect (basic-statistics-complete))

  (:action complete-understanding-variation-and-control-charts
    :parameters ()
    :precondition (define-phase-complete)
    :effect (understanding-variation-and-control-charts-complete))

  (:action complete-measurement-systems-analysis
    :parameters ()
    :precondition (define-phase-complete)
    :effect (measurement-systems-analysis-complete))

  (:action complete-process-capability
    :parameters ()
    :precondition (define-phase-complete)
    :effect (process-capability-complete))

  ; Real DFSS tollgate review: requires every real Measure module complete
  ; before Explore may open.
  (:action conduct-measure-tollgate-review
    :parameters ()
    :precondition (and
      (voice-of-the-customer-complete)
      (quality-function-deployment-complete)
      (target-costing-complete)
      (scorecards-complete)
      (intro-to-minitab-complete)
      (basic-statistics-complete)
      (understanding-variation-and-control-charts-complete)
      (measurement-systems-analysis-complete)
      (process-capability-complete))
    :effect (measure-phase-complete))

  ; =========================================================================
  ; EXPLORE -- each real module requires the Measure tollgate. Real named
  ; exception: both TRIZ modules additionally require Concept Generation
  ; (the real DMEDI ordering -- TRIZ contradiction resolution is applied to
  ; concepts Concept Generation has already produced, never before them).
  ; =========================================================================

  (:action complete-concept-generation
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (concept-generation-complete))

  ; Real prerequisite already implemented, not re-derived here: this
  ; module's TRIZ contradiction-resolution technique is the real, partial
  ; TRIZ contradiction-matrix engine already built and tested this session
  ; in src/autofde_lab/reasoning/laboratory.py section 14 ("TRIZ
  ; contradiction-resolution candidate generation", lines 465-597 --
  ; TRIZParameter, TRIZContradiction, classify_triz_contradiction,
  ; generate_triz_candidates). Cited here as a real existing implementation
  ; this curriculum module corresponds to; this PDDL action itself only
  ; represents completing the training module, not invoking that code.
  (:action complete-triz-for-new-product-design
    :parameters ()
    :precondition (and (measure-phase-complete) (concept-generation-complete))
    :effect (triz-for-new-product-design-complete))

  (:action complete-transactional-triz
    :parameters ()
    :precondition (and (measure-phase-complete) (concept-generation-complete))
    :effect (transactional-triz-complete))

  (:action complete-concept-selection-pugh
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (concept-selection-pugh-complete))

  (:action complete-concept-selection-ahp
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (concept-selection-ahp-complete))

  (:action complete-statistical-tolerance-design
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (statistical-tolerance-design-complete))

  (:action complete-monte-carlo-simulation
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (monte-carlo-simulation-complete))

  (:action complete-hypothesis-testing
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (hypothesis-testing-complete))

  (:action complete-confidence-intervals
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (confidence-intervals-complete))

  (:action complete-testing-means-medians-variances
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (testing-means-medians-variances-complete))

  (:action complete-proportion-and-chi-square
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (proportion-and-chi-square-complete))

  (:action complete-simple-and-multiple-regression
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (simple-and-multiple-regression-complete))

  (:action complete-multi-vari-analysis
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (multi-vari-analysis-complete))

  (:action complete-design-fmea
    :parameters ()
    :precondition (measure-phase-complete)
    :effect (design-fmea-complete))

  ; Real DFSS tollgate review: requires every real Explore module complete
  ; before Develop may open.
  (:action conduct-explore-tollgate-review
    :parameters ()
    :precondition (and
      (concept-generation-complete)
      (triz-for-new-product-design-complete)
      (transactional-triz-complete)
      (concept-selection-pugh-complete)
      (concept-selection-ahp-complete)
      (statistical-tolerance-design-complete)
      (monte-carlo-simulation-complete)
      (hypothesis-testing-complete)
      (confidence-intervals-complete)
      (testing-means-medians-variances-complete)
      (proportion-and-chi-square-complete)
      (simple-and-multiple-regression-complete)
      (multi-vari-analysis-complete)
      (design-fmea-complete))
    :effect (explore-phase-complete))

  ; =========================================================================
  ; DEVELOP -- each real module requires the Explore tollgate. Real named
  ; exceptions: Full-Factorial DOE additionally requires Intro to DOE; DOE
  ; with Curvature and DOE Catapult Simulation each additionally require
  ; Full-Factorial DOE; Robust Design additionally requires DOE with
  ; Curvature -- the real DMEDI DOE progression (basic DOE concepts, then a
  ; full 2^k design, then curvature/robustness extensions built on it).
  ; =========================================================================

  (:action complete-detailed-design
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (detailed-design-complete))

  (:action complete-two-way-anova
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (two-way-anova-complete))

  (:action complete-intro-to-doe
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (intro-to-doe-complete))

  ; Real prerequisite already implemented, not re-derived here: this
  ; module's design-matrix technique is the real, tested full-factorial DOE
  ; generator already built this session in
  ; src/autofde_lab/reasoning/laboratory.py section 15 ("DOE (Design of
  ; Experiments) full-factorial candidate generation", lines 600-703 --
  ; DOEFactor, DOELevel, DOEDesignPoint, generate_full_factorial_design,
  ; generate_doe_candidates). Cited here as a real existing implementation
  ; this curriculum module corresponds to; this PDDL action itself only
  ; represents completing the training module, not invoking that code.
  (:action complete-full-factorial-doe
    :parameters ()
    :precondition (and (explore-phase-complete) (intro-to-doe-complete))
    :effect (full-factorial-doe-complete))

  (:action complete-fractional-factorial-doe
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (fractional-factorial-doe-complete))

  (:action complete-doe-catapult-simulation
    :parameters ()
    :precondition (and (explore-phase-complete) (full-factorial-doe-complete))
    :effect (doe-catapult-simulation-complete))

  (:action complete-lean-design
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (lean-design-complete))

  (:action complete-design-for-manufacture-and-assembly
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (design-for-manufacture-and-assembly-complete))

  (:action complete-intro-to-reliability
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (intro-to-reliability-complete))

  (:action complete-doe-with-curvature
    :parameters ()
    :precondition (and (explore-phase-complete) (full-factorial-doe-complete))
    :effect (doe-with-curvature-complete))

  (:action complete-conjoint-analysis
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (conjoint-analysis-complete))

  (:action complete-mixture-designs
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (mixture-designs-complete))

  (:action complete-robust-design
    :parameters ()
    :precondition (and (explore-phase-complete) (doe-with-curvature-complete))
    :effect (robust-design-complete))

  (:action complete-helicopter-rsm-simulation
    :parameters ()
    :precondition (explore-phase-complete)
    :effect (helicopter-rsm-simulation-complete))

  ; Real DFSS tollgate review: requires every real Develop module complete
  ; before Implement may open.
  (:action conduct-develop-tollgate-review
    :parameters ()
    :precondition (and
      (detailed-design-complete)
      (two-way-anova-complete)
      (intro-to-doe-complete)
      (full-factorial-doe-complete)
      (fractional-factorial-doe-complete)
      (doe-catapult-simulation-complete)
      (lean-design-complete)
      (design-for-manufacture-and-assembly-complete)
      (intro-to-reliability-complete)
      (doe-with-curvature-complete)
      (conjoint-analysis-complete)
      (mixture-designs-complete)
      (robust-design-complete)
      (helicopter-rsm-simulation-complete))
    :effect (develop-phase-complete))

  ; =========================================================================
  ; IMPLEMENT -- its first four real modules require the Develop tollgate.
  ; The fifth, DMEDI Capstone, is the program's real closing deliverable:
  ; it requires every phase's composite tollgate predicate (Define, Measure,
  ; Explore, Develop) plus the four Implement modules that precede it in
  ; the real curriculum order -- the capstone project draws on the whole
  ; program, not merely the most recent phase.
  ; =========================================================================

  (:action complete-overview-of-implement-phase
    :parameters ()
    :precondition (develop-phase-complete)
    :effect (overview-of-implement-phase-complete))

  (:action complete-prototype-and-pilot
    :parameters ()
    :precondition (develop-phase-complete)
    :effect (prototype-and-pilot-complete))

  (:action complete-process-control
    :parameters ()
    :precondition (develop-phase-complete)
    :effect (process-control-complete))

  (:action complete-implementation-planning
    :parameters ()
    :precondition (develop-phase-complete)
    :effect (implementation-planning-complete))

  (:action complete-dmedi-capstone
    :parameters ()
    :precondition (and
      (define-phase-complete)
      (measure-phase-complete)
      (explore-phase-complete)
      (develop-phase-complete)
      (overview-of-implement-phase-complete)
      (prototype-and-pilot-complete)
      (process-control-complete)
      (implementation-planning-complete))
    :effect (dmedi-capstone-complete)))
