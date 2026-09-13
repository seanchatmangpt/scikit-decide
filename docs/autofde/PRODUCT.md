# AutoFDE — the operating model, as a laboratory document

> **Read `docs/autofde/EXPLORE.md` first.** Every surface described here is a prototype in a
> testbed. Nothing in this file is a claim that AutoFDE, the product, does any of it.

## Names, used consistently

| Name | Refers to |
|---|---|
| **Chatman AutoFDE OS** | the product / platform (a different repository, later) |
| **AutoFDE** | the capability category |
| **Azure Breach Clock** | the canonical reference application |
| **scikit-decide** | the academic agent and decision engine — this repository |

This repository is **not** renamed.

## The loop

```text
observe → model → decide → commit → execute within authority → verify → replan
```

Each arrow is a place where something can be refused, and the refusal is the product. A stage that
cannot establish its precondition returns a named refusal rather than a confident guess.

## Manual FDE vs AutoFDE

| | Manual FDE | AutoFDE |
|---|---|---|
| environment | discovered once | continuously observed |
| model | in the engineer's head, then a runbook | live, executable, revised on evidence |
| response | a runbook written and handed over | a bounded commitment that can be superseded |
| when reality changes | summon the humans again | supersede, preserve, replan, request fresh authority |
| authority | a meeting outside the system | bound to action, scope, evidence, population, interval |
| completion | the software was delivered | the consequence was observed, verified, and replayable |

The compressed form: **a manual FDE builds the response system and leaves; AutoFDE stays,
observes when reality changes, and manufactures the next bounded response.**

## The bootstrap-to-breach arc

The case study is not "an Azure breach demo." It is a self-hosting delivery loop:

| Stage | What happens |
|---|---|
| **1 Organize** | a semantic foundation is selected; repository, milestones, issue taxonomy, work items, dependencies, and a POWL project model are manufactured from it |
| **2 Build** | Azure Terraform, adapters, tests, authority structures, and reports are generated |
| **3 Operate** | raw signal → candidate observation → admitted evidence → `AgentSession` → POWL commitment → authority boundary → bounded execution |
| **4 Adapt** | an operational gap becomes a new engineering requirement → updated phase graph → new issue projection → regenerated implementation → resumed incident response |

Stage 4 closing back into Stage 1 is what distinguishes this from a demonstration: the same system
manages the work, manufactures the capability, operates it, and replans **both** the operational
response and the engineering system. It is also the hardest thing here to establish, and the
standing ledger says so rather than implying it.

## What this repository may and may not do

**It computes candidate plans. It does not actuate.** A planner selects; a broker authorizes; an
executor performs; a verifier evaluates. Nothing here carries ambient authority to change the
world, and nothing here should be given receipt, admission, or actuation semantics.

Concretely, within the AutoFDE surfaces:

- the reference POWL executor is an **academic** executor — never citable as evidence of world effect
- `request_authority` requests; it never grants
- a simulated authority grant is a **control**, not evidence that organizational admission works —
  it shows a boolean satisfies a boolean check, exactly as `docs/STATUS.md` pass 4 records for the
  sunset gate
- `terraform apply` is out of bounds for both the Azure and the GitHub provider

## Two partial orders, never conflated

The single most available error in this material, recorded here because it was made once already.

**Provisioning graph** — nodes are API objects, edges mean *needs this object's id to exist*.
**Work-execution graph** — nodes are phases and work items, edges mean *must finish before*.

They are not the same object. Two issues where A blocks B, and two fully independent issues,
produce the *identical* Terraform resource graph. The provisioning graph is invariant under changes
to work order, so it carries no information about it and can never falsify a work-order projection.
Work precedence therefore lives in explicit generated metadata, and the round-trip law reads that,
not the resource graph.

## Standing vocabulary

Every claim about an AutoFDE surface carries one of: `ALIVE`, `PARTIAL_ALIVE`, `BLOCKED:<reason>`,
`BUILD_BROKEN`, `UNKNOWN`, `UNSUPPORTED`, `NOT_RUN` — scoped per boundary, never one field for the
whole system. `.claude/rules/standing-law.md` is the authority.

Three dimensions stay separate: `technicalStanding` may go `ALIVE` on a verified artifact;
`organizationalStanding` stays `UNKNOWN` without accountable customer acceptance;
`enterpriseStanding` requires both. **No component in this repository computes
`organizationalStanding`**, so every AutoFDE row here is a technical claim and must not be re-read
as an enterprise one.

## See also

- `docs/autofde/EXPLORE.md` — the explore/exploit boundary and the extraction manifest
- `.claude/rules/standing-law.md` — the vocabulary
- `.claude/rules/actuation-boundary.md` — what requires authorization before it happens
- `FORWARD_DEPLOYMENT.md` — this repository's role in the portfolio
