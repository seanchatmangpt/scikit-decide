; Real problem instance for domain.pddl in this directory. :init is
; deliberately empty -- neither ~/ggen-marketplace nor ~/wasm4pm has any of
; the four gap-closing artifacts today (verified this session by reading the
; actual current source of both repos, not assumed). :goal is the composite
; state-space-modeling capability.
(define (problem fortune5-k8s-state-space-1)
  (:domain fortune5-k8s-state-space)
  (:init)
  (:goal (has-fortune5-state-space-model)))
