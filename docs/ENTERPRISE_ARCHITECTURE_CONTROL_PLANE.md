# Fortune-5 Enterprise Architecture Control Plane

This layer turns the Fortune-5 combinatorial substrate and TTF5-AR readiness witness
into an explicit enterprise-architecture conformance package.

It is not a customer-adoption engine and it has no actuation authority.

## Architecture equation

```text
O*
× F5 scenario
× TTF5 readiness witness
× enterprise reference profile
× architecture package
× transition DAG
× requirement evidence
× exception evidence
→ EnterpriseArchitectureWitness
```

The result is a deterministic **technical conformance witness**. Organizational and
enterprise standing remain owned by the existing customer-issued adoption path in
`fabric.enterprise_standing`.

## 1. Reference profile

`EnterpriseArchitectureProfile` binds an identified, versioned desired state.

A profile includes mandatory/advisory requirements and exact digests for:

- capability model;
- reference architecture;
- standards catalog;
- NFR/SLO policy;
- security control profile;
- data-governance policy;
- FinOps policy;
- transition principles;
- vendor-exit policy.

Changing any reference artifact changes the profile digest and invalidates stale
conformance submissions.

The built-in F5 benchmark profile is intentionally a **benchmark reference profile**,
not a claim that one universal architecture standard exists for every Fortune-5
company.

## 2. Enterprise architecture package

`EnterpriseArchitecturePackage` binds the admitted subject to the concrete architecture
views that an enterprise architecture review should be able to inspect:

1. capability map;
2. business architecture;
3. information/data architecture;
4. application architecture;
5. technology/reference architecture;
6. security architecture;
7. NFR/SLO envelope;
8. FinOps envelope;
9. governance decisions;
10. transition roadmap.

Missing a required view is a typed refusal. Artifact presence does not imply
conformance.

## 3. Standards and conformance

The default benchmark requirement families are:

| ID | Domain | Level | Intent |
|---|---|---|---|
| `CAP-OWN-001` | Business capability | Mandatory | Accountable capability/outcome/value-stream traceability |
| `DATA-GOV-001` | Information/data | Mandatory | Classification, residency, lineage, retention, stewardship |
| `APP-LIFE-001` | Application | Mandatory | Product ownership, lifecycle, dependencies, retirement |
| `TECH-STD-001` | Technology | Mandatory | Reference architecture and standards compliance |
| `SEC-ZT-001` | Security | Mandatory | Trust boundaries, identity, least privilege, control obligations |
| `RES-RTO-RPO-001` | Resilience | Mandatory | Availability, RTO/RPO, capacity, degradation, recovery |
| `OBS-SLO-001` | Operations | Mandatory | SLOs, telemetry, ownership, alerting, operating evidence |
| `FIN-UNIT-001` | FinOps | Mandatory | Cost envelopes, allocation, unit economics |
| `GOV-ADR-001` | Governance | Mandatory | Decisions, deviations, rationale, authority evidence, review |
| `TRANS-WAVE-001` | Transition | Mandatory | Acyclic waves and reversible dependency boundaries |
| `VENDOR-EXIT-001` | Vendor | Mandatory | Portability, replacement and exit evidence |
| `SUSTAIN-001` | Sustainability | Advisory | Resource/sustainability tradeoffs remain visible |

Mandatory requirements are conjunctive. Eleven PASS decisions cannot compensate for
one unresolved mandatory requirement.

Advisory gaps are reported but do not become hidden mandatory failures.

## 4. NFR/SLO envelope

NFRs are treated as architecture evidence, not prose.

The package binds an `nfr_slo_envelope` artifact and the profile binds the governing
`nfr_slo_policy`. The conformance evidence is expected to cover the service-level and
quality dimensions relevant to the admitted subject, including resilience, capacity,
recovery, operability, and observability.

The verifier does not invent missing SLOs or infer that a diagram satisfies them.

## 5. Security and data governance

Security and data controls are separate mandatory architecture domains.

A subject cannot be technically conformant merely because functional architecture is
complete. `SEC-ZT-001` and `DATA-GOV-001` must each carry explicit evidence bound to the
same subject, package, and profile identities.

This allows regulated/geographic/data-class combinations in the Fortune-5 state space
to be evaluated without changing the authority boundary.

## 6. FinOps and vendor exit

Cost and portability are architecture properties, not post-deployment cleanup.

`FIN-UNIT-001` requires an explicit FinOps envelope. `VENDOR-EXIT-001` requires
portability/replacement/exit evidence so a selected cloud or product does not silently
erase future topology.

This implements combinatorial maximalism at the enterprise boundary: reversible lawful
options are preserved until an authorized irreversible choice is made.

## 7. Transition architecture

`TransitionPlan` is an immutable dependency DAG.

It provides:

- named transition waves;
- dependency edges;
- deterministic topological order;
- subject-bound digest identity;
- typed refusal of missing nodes, self-dependencies, duplicates, and cycles.

A transition plan is **intent**, not execution. It grants no deployment or mutation
authority.

## 8. Exception governance

A mandatory FAIL remains a failure unless explicit exception evidence is supplied.

Exception evidence binds:

```text
requirement
× subject
× architecture package
× reference profile
× external authority decision
× authority evidence digest
× approver identity digest
× authority-verifier IRI
× issue/expiry interval
× compensating-control digests
```

An externally asserted `APPROVED` exception is usable for technical conformance only
while it is in its validity window. The witness reports it as
`CONFORMANT_WITH_EXCEPTIONS` and increments `exception_debt`.

The failed requirement is never rewritten to PASS.

This verifier validates the shape, identity, time window and evidence binding of the
supplied exception decision. It does **not** grant the approver authority. Customer and
organizational authority must be established by the appropriate external authority
surface.

Expired, rejected, unknown, unbound, or orphan exception evidence fails closed.

## 9. Relationship to TTF5-AR

Enterprise architecture conformance is downstream of an exact TTF5 readiness witness.

The submission binds the `ReadinessWitness.witness_digest`. Verification refuses:

- a different readiness witness;
- a different readiness subject;
- a readiness witness that is not `ALIVE`.

Therefore a package cannot promote partial technical readiness into enterprise
architecture conformance.

## 10. Deterministic replay

Every enterprise-architecture witness binds:

- subject digest;
- TTF5 witness digest;
- profile digest;
- package digest;
- transition-plan digest;
- submission digest;
- verification time;
- mandatory/advisory outcomes;
- exception debt;
- transition order.

`EnterpriseArchitectureVerifier.replay()` recomputes the witness at the original
verification boundary and refuses any divergence.

## 11. Public-ontology correspondence

The implementation remains a projection over the repository's public-ontology
interchange vocabulary:

```text
ArchitecturePackage     → prov:Entity
ArchitectureEvidence    → prov:Entity
ArchitecturePolicy      → odrl:Policy
ArchitectureRequirement → odrl:Constraint
ArchitectureConcept     → skos:Concept
TransitionActivity      → prov:Activity
```

The local Fortune-5 ontology remains the possibility graph; it is not promoted into an
actuation authority or a second enterprise truth source.

## 12. Standing

A successful verifier result establishes only:

```text
technicalStanding = ALIVE
conformanceStatus = CONFORMANT | CONFORMANT_WITH_EXCEPTIONS
```

It does not establish:

```text
organizationalStanding = ALIVE
enterpriseStanding = ALIVE
customer adoption = ADOPTED
actuation authority
```

Those remain external evidence/authority transitions.

## 13. Falsifiers

Reject the enterprise-architecture conformance standing if any of the following becomes
possible:

- a mandatory requirement is compensated by unrelated PASS results;
- a missing mandatory requirement is treated as PASS;
- evidence binds another subject, package, or profile;
- profile/reference-artifact drift does not invalidate a submission;
- a non-ALIVE TTF5 witness is promoted to EA conformance;
- a transition DAG can contain a cycle or unknown node;
- an expired/rejected exception masks a mandatory failure;
- an exception silently rewrites a failed requirement to PASS;
- exception evidence manufactures customer or organizational authority;
- replay diverges;
- the architecture package gains ambient deployment/actuation authority.

## 14. Qualification

The exact-head TTF5 court executes the EA Chicago tests together with TTF5 and the
existing Fortune-5 state-space court.

```bash
PYTHONPATH=src python -m pytest -q \
  tests/fortune5/test_enterprise_architecture.py \
  tests/fortune5/test_readiness.py \
  tests/fortune5/test_space.py
```

Repository-wide qualification and the independent Fortune-5 ggen CMD court remain
separate required evidence. A queued workflow, documentation artifact, or architecture
diagram is not a crown.

## 15. Qualification receipt model

Exact-head standing is SHA-scoped. Any repository edit changes subject identity and
requires a new exact-head qualification. The repository records the stable proof
contract; run-specific standing belongs in external receipt metadata associated with the
exact candidate SHA.

```text
PR head SHA
× exact-head TTF5/EA/state-space court
× exact-head Fortune-5 ggen manufacture court
× exact-head repository qualification
× exact-head Challenger load court
× head-bound artifact digest
→ scoped technical standing
```
