---
paths:
  - "tests/ecosystem/**"
  - "ontology/**"
  - "docs/ecosystem-standing.md"
  - "src/autofde_lab/fabric/fde.py"
  - "src/autofde_lab/fabric/recursive_controller.py"
---

# FDE authority boundary — compiling a customer model is not holding customer authority

The ecosystem separation (`.claude/rules/ecosystem-boundary.md`) closes a **technical** chain:
authority → plan → geometry → schedule → manufacture → verification. An enterprise transition
needs a second chain the technical one cannot supply: customer reality → admitted customer
model → bounded organizational authority → technical consequence → accountable acceptance →
adopted organizational capability. The Forward-Deployed Architect owns that bridge.

The FDE is **not** a manual approval button, and not a human in a loop that would otherwise be
automatic. The FDE compiles a customer model as a *falsifiable hypothesis*, presents it for
validation or falsification, converts organizational decision rights into bounded
machine-enforceable authority, defines the business postconditions that make a technical
consequence matter, presents independently verified evidence, and obtains explicit authority
for irreversible transitions.

## The rule

> The FDE may compile models, structure authority, map customer semantics, and present
> evidence. The FDE may **not** invent customer authority, self-admit observations,
> self-certify manufactured artifacts, or authorize irreversible sunset without the accountable
> customer decision right.

Same shape as the technical boundary and for the same reason: a component that infers the
spec, generates the implementation, evaluates it *and* certifies it is self-attesting. An FDE
that compiles the customer model *and* grants the authority that model implies is the
organizational instance of that circularity.

## Seven kinds, non-interchangeable

Conflating any two of these is the failure this rule exists to prevent. Each has a distinct
issuer; none substitutes for another, in either direction.

| Kind | Issued by | Is not |
|---|---|---|
| FDE recommendation | the FDE | authority to act |
| customer authority grant | a named customer decision right | an unchallenged recommendation |
| broker authorization | MFW's broker, per occurrence | a standing grant |
| technical consequence | the manufactured, verified artifact | value delivered |
| verifier verdict | an independent verifier | the producer's own claim |
| adoption decision | the customer operating owner | a successful deployment |
| sunset authorization | the accountable retirement decision right | an adoption decision |

Deployment, file creation, and receipt verification are **not** organizational adoption. A
green receipt says an artifact was manufactured as specified; it says nothing about whether the
organization took the capability up, or whether the business postconditions the FDE agreed in
advance were met.

## A naked boolean is not organizational authority

`~/ggen-legacy/appliance/bin/decision-engine.py` (38 lines, read 2026-08-06) fail-closes sunset
on three reports (verifier `ALIVE`, cross-check `ALIVE`, replay `REPLAY_MATCH`), seven
capability-closure counters all zero, and `customer_authorized_retirement is True`. That gate
is correct and must never be replaced by a local simulation. But the last conjunct is a bare
boolean in a manifest: a true value there is currently *unattributable*.

For that flag to carry organizational authority it must resolve to a record naming all of:

1. the authority — a named holder of the retirement decision right;
2. the predecessor identity being retired, specifically;
3. the replacement identity, specifically, and independently verified;
4. the evidence set actually reviewed;
5. a timestamp;
6. the scope conditions under which the grant holds.

Absent that record the flag is an assertion by whoever wrote the JSON. Do not treat writing
`true` as obtaining authority.

## Standing consequence

Nothing under these paths may report `enterpriseStanding` on technical evidence alone. A
verified artifact establishes `technicalStanding` and leaves `organizationalStanding` `UNKNOWN`
until an accountable acceptance exists — see `.claude/rules/standing-law.md`. As of this
session no component computes `organizationalStanding`; the FDE rail is being built and has not
run.

## See also

- `.claude/rules/standing-law.md` — the three standing dimensions and the status vocabulary.
- `.claude/rules/ecosystem-boundary.md` — the technical separation this file extends.
- `.claude/rules/actuation-boundary.md` — why a planner result is never an actuation.
- `docs/ecosystem-standing.md` — the cross-repo evidence ledger.
