# School Library Recommendation Copilot — DfCM Runnable POC

Synthetic proof-of-concept for the Qvest interview prompt.

## What this demonstrates

- Hybrid recommendation over circulation history + catalog metadata.
- Bounded language layer that produces structured constraints and one admitted objective enum.
- **Design for Combinatorial Maximalism (DfCM):** manufacture 16 reversible ranking policies before selecting one.
- Formal policy admission with typed `REFUSED:*` results for malformed policies.
- Synthetic temporal holdout + fixed intent probes as a bounded falsifier court.
- Pareto-frontier preservation before late objective-based selection.
- Candidate-level admission/refusal trace, including why books were excluded.
- Deterministic SHA-256 replay receipt binding datasets, request, policy space, selected policy, and output.
- Explicit `SELECT_ONLY:NO_ACTUATION` authority boundary.
- No student PII and no real school/client data.

## DfCM execution path

```text
request
  -> bounded parse
  -> manufacture policy graph (2 x 2 x 2 x 2 = 16)
  -> formally admit/refuse each policy
  -> synthetic falsifier court
  -> preserve non-dominated Pareto frontier
  -> select one policy as late as possible
  -> rank admitted catalog candidates
  -> emit candidate trace + deterministic replay receipt
```

The policy axes are content, co-circulation, librarian intent, and novelty. A small curated-catalog signal remains present in every policy. The court is intentionally capped at `top_k=3` because a top-5 hit-rate is too permissive for this 12-book synthetic catalog.

## Run the CLI demo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python demo_cli.py
```

The CLI prints the complete receipt, including the selected policy, all policy evaluations, the preserved frontier, recommendation signals, and every candidate admission/refusal decision.

## Optional Streamlit UI

```bash
streamlit run app.py
```

Try phrases such as:

- `Something funny, preferably a mystery, and not part of a long series.`
- `Surprise me with something different.` → bounded `discovery` objective
- `Give me something similar to what they already enjoy.` → bounded `familiar` objective

The language layer does **not** directly rank books and does **not** provide catalog facts.

## Validate

```bash
pytest -q
python demo_cli.py
python -m py_compile app.py dfcm.py llm.py models.py recommender.py demo_cli.py \
  tests/test_recommender.py tests/test_dfcm.py
```

## Standing and falsifiers

This demo can prove deterministic behavior against its synthetic subject. It cannot prove educational benefit, production safety, district acceptance, or student outcomes. Those remain outside the admitted evidence boundary until real evaluation exists.

A DfCM claim is falsified if policy manufacture is non-deterministic, a generated policy fails admission, receipt replay changes without an input change, an excluded candidate lacks a typed reason, or selection escapes the preserved lawful frontier.

## Production extension path

1. Replace synthetic CSVs with district-provided catalog and circulation exports.
2. Add district-controlled pseudonymous student identifiers.
3. Version the recommender, parser contract, policy-space definition, and catalog snapshot.
4. Replace synthetic probes with approved offline evaluation scenarios and temporal holdouts.
5. Add fairness, grade-band, accessibility, language, and collection-development constraints as new reversible policy dimensions rather than hard-coding a single choice.
6. Pilot with librarians in assisted mode before any student-facing rollout.
7. Keep downstream actions outside this selector and behind an independently authorized, receipted actuation boundary.
