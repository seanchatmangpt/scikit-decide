(define (problem 80_identity_compromise)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    identity-compromise - subject
    security-strategy - capability
    agent-service - workload
    sensitive-data - data
    prod-cloud recovery-cloud - cloud
    prod-region isolation-region - region
    tier0 - tier
    identity key-management logging incident-response - control)
  (:init
    (subject-admitted identity-compromise)
    (capability-required security-strategy)
    (workload-required agent-service)
    (data-required sensitive-data)
    (tier-required tier0)
    (control-required identity)
    (control-required key-management)
    (control-required logging)
    (control-required incident-response)
    (cloud-allowed prod-cloud)
    (cloud-allowed recovery-cloud)
    (region-allowed prod-region)
    (region-allowed isolation-region))
  (:goal (and
    (architecture-candidate identity-compromise)
    (verifier-ready identity-compromise)
    (recovery-ready identity-compromise)
    (brce-handoff-ready identity-compromise)))
)
