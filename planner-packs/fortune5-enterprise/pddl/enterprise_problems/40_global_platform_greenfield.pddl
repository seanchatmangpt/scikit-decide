(define (problem 40_global_platform_greenfield)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    global-platform - subject
    digital-platform - capability
    critical-service - workload
    regulated-data - data
    azure aws gcp - cloud
    primary-region secondary-region - region
    tier1 - tier
    identity data-protection logging recovery - control)
  (:init
    (subject-admitted global-platform)
    (capability-required digital-platform)
    (workload-required critical-service)
    (data-required regulated-data)
    (tier-required tier1)
    (control-required identity)
    (control-required data-protection)
    (control-required logging)
    (control-required recovery)
    (cloud-allowed azure)
    (cloud-allowed aws)
    (cloud-allowed gcp)
    (region-allowed primary-region)
    (region-allowed secondary-region))
  (:goal (and
    (architecture-candidate global-platform)
    (verifier-ready global-platform)
    (recovery-ready global-platform)
    (brce-handoff-ready global-platform)))
)
