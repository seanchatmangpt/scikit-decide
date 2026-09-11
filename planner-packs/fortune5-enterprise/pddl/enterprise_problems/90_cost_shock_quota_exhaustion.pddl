(define (problem 90_cost_shock_quota_exhaustion)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    cost-shock - subject
    finance - capability
    elastic-service - workload
    operational-data - data
    cloud-a cloud-b - cloud
    region-a region-b - region
    tier1 - tier
    identity logging change-control evidence - control)
  (:init
    (subject-admitted cost-shock)
    (capability-required finance)
    (workload-required elastic-service)
    (data-required operational-data)
    (tier-required tier1)
    (control-required identity)
    (control-required logging)
    (control-required change-control)
    (control-required evidence)
    (cloud-allowed cloud-a)
    (cloud-allowed cloud-b)
    (region-allowed region-a)
    (region-allowed region-b))
  (:goal (and
    (architecture-candidate cost-shock)
    (verifier-ready cost-shock)
    (recovery-ready cost-shock)
    (brce-handoff-ready cost-shock)))
)
