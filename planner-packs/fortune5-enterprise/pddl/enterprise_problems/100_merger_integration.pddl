(define (problem 100_merger_integration)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    merger-integration - subject
    portfolio-management - capability
    enterprise-apps - workload
    mixed-data - data
    company-a-cloud company-b-cloud - cloud
    company-a-region company-b-region - region
    tier2 - tier
    identity data-protection logging third-party-risk - control)
  (:init
    (subject-admitted merger-integration)
    (capability-required portfolio-management)
    (workload-required enterprise-apps)
    (data-required mixed-data)
    (tier-required tier2)
    (control-required identity)
    (control-required data-protection)
    (control-required logging)
    (control-required third-party-risk)
    (cloud-allowed company-a-cloud)
    (cloud-allowed company-b-cloud)
    (region-allowed company-a-region)
    (region-allowed company-b-region))
  (:goal (and
    (architecture-candidate merger-integration)
    (verifier-ready merger-integration)
    (recovery-ready merger-integration)
    (brce-handoff-ready merger-integration)))
)
