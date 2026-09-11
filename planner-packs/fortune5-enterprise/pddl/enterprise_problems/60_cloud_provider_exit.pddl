(define (problem 60_cloud_provider_exit)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    provider-exit - subject
    vendor-strategy - capability
    portable-service - workload
    enterprise-data - data
    incumbent-cloud target-cloud - cloud
    source-region target-region - region
    tier1 - tier
    identity data-protection supply-chain evidence - control)
  (:init
    (subject-admitted provider-exit)
    (capability-required vendor-strategy)
    (workload-required portable-service)
    (data-required enterprise-data)
    (tier-required tier1)
    (control-required identity)
    (control-required data-protection)
    (control-required supply-chain)
    (control-required evidence)
    (cloud-allowed incumbent-cloud)
    (cloud-allowed target-cloud)
    (region-allowed source-region)
    (region-allowed target-region))
  (:goal (and
    (architecture-candidate provider-exit)
    (verifier-ready provider-exit)
    (recovery-ready provider-exit)
    (brce-handoff-ready provider-exit)))
)
