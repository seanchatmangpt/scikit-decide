# School Library Recommendation Copilot — Runnable POC

Synthetic proof-of-concept for the Qvest interview prompt.

## What this demonstrates

- Hybrid recommendation over circulation history + catalog metadata.
- Bounded language layer that turns a librarian request into structured constraints.
- Explicit recommendation receipts with ranking signals.
- No student PII and no real school/client data.
- The LLM layer does not rank books or invent facts.

## Run the CLI demo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python demo_cli.py
```

## Optional Streamlit UI

```bash
streamlit run app.py
```

## Validate

```bash
pytest -q
```

## Production extension path

1. Replace synthetic CSVs with district-provided catalog and circulation exports.
2. Add district-controlled pseudonymous student identifiers.
3. Version the recommender, prompt contract, and catalog snapshot.
4. Run temporal holdout evaluation before any pilot.
5. Pilot with librarians in assisted mode before student-facing rollout.
