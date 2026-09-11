# AutoFDE Lab Diataxis Documentation

This directory organizes documentation by the [Diataxis](https://diataxis.fr)
framework: four distinct modes, each answering a different kind of question.
The first worked example across all four is the already-merged autonomic
life-planning case study (`src/autofde_lab/agent/life_autonomic_case_study.py`,
PR #92, merge `6d0a3aed`) — see
[the case-study record](../case-studies/life-autonomic-controller.md) for its
own standing/falsifier ledger, which this Diataxis set links to rather than
duplicates.

| Mode | Question it answers | Doc |
|---|---|---|
| Tutorial | "Teach me by doing" | [Run the autonomic life planning case study](tutorials/life-autonomic-case-study-walkthrough.md) |
| How-to guide | "How do I achieve X with what I already know?" | [Adapt the case study to your own planning world](how-to/adapt-life-case-study-to-your-own-planning-world.md) |
| Reference | "What exactly does this module expose?" | [Life autonomic case study API reference](reference/life-autonomic-case-study-api.md) |
| Explanation | "Why does this exist and why does it look this way?" | [Why a bounded life-planning case study](explanation/why-a-bounded-life-planning-case-study.md) |

## Reading order

- New to the case study: start with the **Tutorial**, then the **Explanation**
  to understand why it's shaped the way it is.
- Building your own bounded planning subject on the same kernel: start with
  the **How-to guide**, keep the **Reference** open alongside it.
- Auditing or reviewing the module: the **Reference** is the precise surface;
  the **Explanation** covers the design decisions and named non-goals.

## Standing note

Per `docs/CLAUDE.md`: docs never create standing. Every "this works" claim in
these four documents points at a real command and its real output (the
Chicago-style test at `tests/agent/test_life_autonomic_case_study.py`,
`3 passed`) rather than asserting behavior in prose alone. If code and docs
ever disagree, the code and its test suite are the witness — file a
correction here, don't just edit the claim away.
