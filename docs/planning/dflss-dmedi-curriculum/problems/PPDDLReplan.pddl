; Real per-planner problem instance for domain.pddl in the parent directory,
; generated for the real registered planner "PPDDLReplan" -- one of the 57 real
; planners in PRIMARY_PLANNERS + NOVELTY_ORACLES
; (src/autofde_lab/planner_league/catalog.py), assigned here along the real
; "planner" axis already named in that module's own EXPERIMENT_DIMENSIONS
; tuple. :init is deliberately empty, matching problem.pddl in this same
; parent directory -- this is a candidate-plan problem instance for the real
; DMEDI curriculum module order, not a record of any learner's actual
; progress (no module is asserted complete without evidence). :goal is the
; program's real closing deliverable, the DMEDI Capstone -- identical to
; problem.pddl's goal. The only thing that varies across this directory's 57
; files is which real planner is named to attempt this identical problem;
; :init and :goal never vary by planner. File identity ("PPDDLReplan.pddl") and
; problem identity ("dflss-dmedi-curriculum-for-ppddlreplan") are kept in lockstep
; by construction, per this session's task specification.
(define (problem dflss-dmedi-curriculum-for-ppddlreplan)
  (:domain dflss-dmedi-curriculum)
  (:init)
  (:goal (dmedi-capstone-complete)))
