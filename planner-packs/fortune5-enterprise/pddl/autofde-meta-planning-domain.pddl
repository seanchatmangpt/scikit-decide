(define (domain autofde-meta-planning)
  (:requirements :strips :typing)
  (:types planner role world subject)
  (:predicates
    (observation-admitted ?s - subject)
    (transition-receipted ?s - subject ?w - world)
    (planner-available ?p - planner)
    (compatible ?p - planner ?r - role)
    (constructor-role ?r - role)
    (falsifier-role ?r - role)
    (world-allowed ?w - world)
    (world-manufactured ?w - world ?s - subject)
    (planner-bound ?p - planner ?r - role)
    (problem-formulated ?s - subject ?r - role ?w - world)
    (league-open ?s - subject ?w - world)
    (candidate-plan ?p - planner ?r - role ?w - world)
    (counterplan ?p - planner ?r - role ?w - world)
    (falsification-complete ?s - subject ?w - world)
    (survivor-selected ?p - planner ?r - role ?w - world)
    (verifier-ready ?s - subject ?w - world)
    (recovery-ready ?s - subject ?w - world)
    (intent-ready ?p - planner ?r - role ?w - world)
    (handoff-ready ?s - subject ?w - world)
    (previous-planner ?p - planner)
    (different-planner ?p1 - planner ?p2 - planner)
    (planner-switched ?p1 - planner ?p2 - planner)
    (semantic-delta-captured ?s - subject)
    (ggen-projection-ready ?s - subject)
    (closed-class ?s - subject))

  (:action manufacture-world
    :parameters (?w - world ?s - subject)
    :precondition (and (observation-admitted ?s) (world-allowed ?w))
    :effect (world-manufactured ?w ?s))

  (:action bind-planner-to-role
    :parameters (?p - planner ?r - role)
    :precondition (and (planner-available ?p) (compatible ?p ?r))
    :effect (planner-bound ?p ?r))

  (:action formulate-role-problem
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (and (world-manufactured ?w ?s) (planner-bound ?p ?r))
    :effect (problem-formulated ?s ?r ?w))

  (:action open-role-conditioned-league
    :parameters (?s - subject ?rc - role ?rf - role ?w - world)
    :precondition (and
      (problem-formulated ?s ?rc ?w)
      (problem-formulated ?s ?rf ?w)
      (constructor-role ?rc)
      (falsifier-role ?rf))
    :effect (league-open ?s ?w))

  (:action construct-candidate-plan
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (and
      (league-open ?s ?w)
      (planner-bound ?p ?r)
      (constructor-role ?r)
      (problem-formulated ?s ?r ?w))
    :effect (candidate-plan ?p ?r ?w))

  (:action construct-counterplan
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (and
      (league-open ?s ?w)
      (planner-bound ?p ?r)
      (falsifier-role ?r)
      (problem-formulated ?s ?r ?w))
    :effect (counterplan ?p ?r ?w))

  (:action falsify-candidate
    :parameters (?s - subject ?pc - planner ?rc - role ?pf - planner ?rf - role ?w - world)
    :precondition (and
      (candidate-plan ?pc ?rc ?w)
      (counterplan ?pf ?rf ?w)
      (constructor-role ?rc)
      (falsifier-role ?rf))
    :effect (falsification-complete ?s ?w))

  (:action select-surviving-candidate
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (and (candidate-plan ?p ?r ?w) (falsification-complete ?s ?w))
    :effect (survivor-selected ?p ?r ?w))

  (:action construct-verifier
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (survivor-selected ?p ?r ?w)
    :effect (verifier-ready ?s ?w))

  (:action construct-recovery
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (survivor-selected ?p ?r ?w)
    :effect (recovery-ready ?s ?w))

  (:action construct-next-edge-intent
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (and
      (survivor-selected ?p ?r ?w)
      (verifier-ready ?s ?w)
      (recovery-ready ?s ?w))
    :effect (intent-ready ?p ?r ?w))

  (:action construct-brce-handoff
    :parameters (?s - subject ?p - planner ?r - role ?w - world)
    :precondition (and
      (intent-ready ?p ?r ?w)
      (verifier-ready ?s ?w)
      (recovery-ready ?s ?w))
    :effect (handoff-ready ?s ?w))

  ;; This can fire only in a NEW episode seeded with an independently observed receipt.
  (:action switch-planner-after-observation
    :parameters (?s - subject ?w - world ?old - planner ?new - planner ?r - role)
    :precondition (and
      (transition-receipted ?s ?w)
      (previous-planner ?old)
      (planner-available ?new)
      (compatible ?new ?r)
      (different-planner ?old ?new))
    :effect (and (planner-bound ?new ?r) (planner-switched ?old ?new)))

  (:action capture-receipted-semantic-delta
    :parameters (?s - subject ?w - world)
    :precondition (transition-receipted ?s ?w)
    :effect (semantic-delta-captured ?s))

  (:action project-solved-cognition-with-ggen
    :parameters (?s - subject)
    :precondition (semantic-delta-captured ?s)
    :effect (ggen-projection-ready ?s))

  (:action close-solved-class
    :parameters (?s - subject)
    :precondition (ggen-projection-ready ?s)
    :effect (closed-class ?s))
)
