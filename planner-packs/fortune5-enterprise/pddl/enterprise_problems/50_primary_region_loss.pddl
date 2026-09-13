(define (problem 50_primary_region_loss)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    region-loss - subject
    business-continuity - capability
    critical-service - workload
    critical-data - data
    primary-cloud alternate-cloud - cloud
    failed-region recovery-region - region
    tier0 - tier
    identity recovery logging change-control - control)
  (:init
    (subject-admitted region-loss)
    (capability-required business-continuity)
    (workload-required critical-service)
    (data-required critical-data)
    (tier-required tier0)
    (control-required identity)
    (control-required recovery)
    (control-required logging)
    (control-required change-control)
    (cloud-allowed primary-cloud)
    (cloud-allowed alternate-cloud)
    (region-allowed failed-region)
    (region-allowed recovery-region))
  (:goal (and
    (architecture-candidate region-loss)
    (verifier-ready region-loss)
    (recovery-ready region-loss)
    (brce-handoff-ready region-loss)))
)
