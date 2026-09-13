(define (problem 110_ai_agent_governance)
  (:domain autofde-fortune5-enterprise-architecture)
  (:objects
    ai-agent-governance - subject
    technology-strategy - capability
    agentic-platform - workload
    restricted-context - data
    ai-cloud enterprise-cloud - cloud
    ai-region enterprise-region - region
    tier1 - tier
    identity ai-governance data-protection evidence - control)
  (:init
    (subject-admitted ai-agent-governance)
    (capability-required technology-strategy)
    (workload-required agentic-platform)
    (data-required restricted-context)
    (tier-required tier1)
    (control-required identity)
    (control-required ai-governance)
    (control-required data-protection)
    (control-required evidence)
    (cloud-allowed ai-cloud)
    (cloud-allowed enterprise-cloud)
    (region-allowed ai-region)
    (region-allowed enterprise-region))
  (:goal (and
    (architecture-candidate ai-agent-governance)
    (verifier-ready ai-agent-governance)
    (recovery-ready ai-agent-governance)
    (brce-handoff-ready ai-agent-governance)))
)
