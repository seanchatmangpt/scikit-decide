(define (domain autofde-fortune5-enterprise-architecture)
  (:requirements :strips :typing)
  (:types subject capability workload data cloud region tier control concern)
  (:predicates
    (subject-admitted ?s - subject)
    (capability-required ?c - capability)
    (workload-required ?w - workload)
    (data-required ?d - data)
    (cloud-allowed ?c - cloud)
    (region-allowed ?r - region)
    (tier-required ?t - tier)
    (control-required ?c - control)
    (concern-required ?c - concern)

    (business-bound ?s - subject ?c - capability)
    (workload-classified ?s - subject ?w - workload)
    (data-classified ?s - subject ?d - data)
    (tier-bound ?s - subject ?t - tier)
    (control-bound ?s - subject ?c - control)
    (placement-enumerated ?s - subject ?c - cloud ?r - region)
    (sovereignty-assessed ?s - subject)
    (identity-assessed ?s - subject)
    (resilience-assessed ?s - subject)
    (observability-assessed ?s - subject)
    (cost-assessed ?s - subject)
    (exit-assessed ?s - subject)
    (operating-model-assessed ?s - subject)
    (portfolio-assessed ?s - subject)
    (architecture-candidate ?s - subject)
    (verifier-ready ?s - subject)
    (recovery-ready ?s - subject)
    (next-edge-ready ?s - subject)
    (brce-handoff-ready ?s - subject))

  (:action bind-business-capability
    :parameters (?s - subject ?c - capability)
    :precondition (and (subject-admitted ?s) (capability-required ?c))
    :effect (business-bound ?s ?c))

  (:action classify-workload
    :parameters (?s - subject ?w - workload)
    :precondition (and (subject-admitted ?s) (workload-required ?w))
    :effect (workload-classified ?s ?w))

  (:action classify-data
    :parameters (?s - subject ?d - data)
    :precondition (and (subject-admitted ?s) (data-required ?d))
    :effect (data-classified ?s ?d))

  (:action bind-service-tier
    :parameters (?s - subject ?t - tier)
    :precondition (and (subject-admitted ?s) (tier-required ?t))
    :effect (tier-bound ?s ?t))

  (:action bind-control-baseline
    :parameters (?s - subject ?c - control)
    :precondition (and (subject-admitted ?s) (control-required ?c))
    :effect (control-bound ?s ?c))

  (:action enumerate-placement
    :parameters (?s - subject ?c - cloud ?r - region)
    :precondition (and (subject-admitted ?s) (cloud-allowed ?c) (region-allowed ?r))
    :effect (placement-enumerated ?s ?c ?r))

  (:action assess-sovereignty
    :parameters (?s - subject ?d - data)
    :precondition (data-classified ?s ?d)
    :effect (sovereignty-assessed ?s))

  (:action assess-identity
    :parameters (?s - subject ?c - control)
    :precondition (control-bound ?s ?c)
    :effect (identity-assessed ?s))

  (:action assess-resilience
    :parameters (?s - subject ?t - tier)
    :precondition (tier-bound ?s ?t)
    :effect (resilience-assessed ?s))

  (:action assess-observability
    :parameters (?s - subject ?w - workload)
    :precondition (workload-classified ?s ?w)
    :effect (observability-assessed ?s))

  (:action assess-cost
    :parameters (?s - subject ?c - cloud ?r - region)
    :precondition (placement-enumerated ?s ?c ?r)
    :effect (cost-assessed ?s))

  (:action assess-exit
    :parameters (?s - subject ?c - cloud ?r - region)
    :precondition (placement-enumerated ?s ?c ?r)
    :effect (exit-assessed ?s))

  (:action assess-operating-model
    :parameters (?s - subject ?c - capability)
    :precondition (business-bound ?s ?c)
    :effect (operating-model-assessed ?s))

  (:action assess-portfolio
    :parameters (?s - subject ?c - capability)
    :precondition (business-bound ?s ?c)
    :effect (portfolio-assessed ?s))

  (:action construct-enterprise-architecture-candidate
    :parameters (?s - subject)
    :precondition (and
      (sovereignty-assessed ?s)
      (identity-assessed ?s)
      (resilience-assessed ?s)
      (observability-assessed ?s)
      (cost-assessed ?s)
      (exit-assessed ?s)
      (operating-model-assessed ?s)
      (portfolio-assessed ?s))
    :effect (architecture-candidate ?s))

  (:action construct-verifier
    :parameters (?s - subject)
    :precondition (architecture-candidate ?s)
    :effect (verifier-ready ?s))

  (:action construct-recovery
    :parameters (?s - subject)
    :precondition (architecture-candidate ?s)
    :effect (recovery-ready ?s))

  (:action construct-next-edge
    :parameters (?s - subject)
    :precondition (and (architecture-candidate ?s) (verifier-ready ?s) (recovery-ready ?s))
    :effect (next-edge-ready ?s))

  (:action construct-brce-handoff
    :parameters (?s - subject)
    :precondition (and (next-edge-ready ?s) (verifier-ready ?s) (recovery-ready ?s))
    :effect (brce-handoff-ready ?s))
)
