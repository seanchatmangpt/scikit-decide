; Real problem instance for domain.pddl in this directory. :init is
; deliberately empty -- this is a candidate-plan problem instance for the
; real DMEDI curriculum module order, not a record of any learner's actual
; progress (no module is asserted complete without evidence). :goal is the
; program's real closing deliverable, the DMEDI Capstone.
(define (problem dflss-dmedi-curriculum-1)
  (:domain dflss-dmedi-curriculum)
  (:init)
  (:goal (dmedi-capstone-complete)))
