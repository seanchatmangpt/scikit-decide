(define (problem 70_data_sovereignty_split)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    sovereignty-split - subject
    data-strategy - capability
    global-service - workload
    restricted-data - data
    cloud-a cloud-b - cloud
    jurisdiction-a jurisdiction-b - region
    tier1 - tier
    identity data-protection privacy logging - control)
  (:init
    (subject-admitted sovereignty-split)
    (capability-required data-strategy)
    (workload-required global-service)
    (data-required restricted-data)
    (tier-required tier1)
    (control-required identity)
    (control-required data-protection)
    (control-required privacy)
    (control-required logging)
    (cloud-allowed cloud-a)
    (cloud-allowed cloud-b)
    (region-allowed jurisdiction-a)
    (region-allowed jurisdiction-b))
  (:goal (and
    (architecture-candidate sovereignty-split)
    (verifier-ready sovereignty-split)
    (recovery-ready sovereignty-split)
    (brce-handoff-ready sovereignty-split)))
)
