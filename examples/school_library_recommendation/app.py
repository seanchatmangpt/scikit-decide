from pathlib import Path

from llm import parse_librarian_request
from recommender import HybridRecommender, load_data

try:
    import streamlit as st
except ImportError as exc:
    raise SystemExit(
        "Streamlit is not installed. Run: pip install -r requirements.txt"
    ) from exc

DATA_DIR = Path(__file__).parent / "data"
catalog, circulation = load_data(DATA_DIR)
recommender = HybridRecommender(catalog, circulation)

st.title("School Library Recommendation Copilot")
st.caption(
    "Synthetic POC data. LLM layer is represented by an offline schema parser for repeatable demo execution."
)
student_id = st.selectbox("Student", sorted(circulation.student_id.unique()), index=3)
request = st.text_input(
    "Librarian request",
    "Something funny, preferably a mystery, and not part of a long series.",
)

if st.button("Recommend"):
    intent = parse_librarian_request(request)
    st.subheader("Structured intent")
    st.json(intent.__dict__)
    st.subheader("Recommendations")
    for r in recommender.recommend(student_id, intent):
        with st.expander(f"{r.title} — score {r.score}"):
            st.write(r.explanation)
            st.json(r.signals)
            st.caption("LLM changed ranking: no. LLM supplied facts: no.")
