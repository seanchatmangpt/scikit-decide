from pathlib import Path

from dfcm import execute_dfcm, verify_receipt
from llm import parse_librarian_request
from recommender import load_data

try:
    import streamlit as st
except ImportError as exc:
    raise SystemExit(
        "Streamlit is not installed. Run: pip install -r requirements.txt"
    ) from exc

DATA_DIR = Path(__file__).parent / "data"
catalog, circulation = load_data(DATA_DIR)

st.title("School Library Recommendation Copilot")
st.caption(
    "Synthetic POC data. DfCM manufactures lawful ranking policies, preserves the "
    "Pareto frontier, and selects late. The language layer never ranks books."
)
student_id = st.selectbox("Student", sorted(circulation.student_id.unique()), index=3)
request = st.text_input(
    "Librarian request",
    "Something funny, preferably a mystery, and not part of a long series.",
)

if st.button("Recommend"):
    intent = parse_librarian_request(request)
    receipt = execute_dfcm(
        catalog=catalog,
        circulation=circulation,
        student_id=student_id,
        raw_request=request,
        intent=intent,
        top_k=5,
    )

    st.subheader("Structured intent")
    st.json(receipt["request"]["structured_intent"])

    st.subheader("DfCM selection")
    st.write(
        f"Manufactured {receipt['dfcm']['manufactured_policy_count']} policies; "
        f"preserved {len(receipt['dfcm']['pareto_frontier_policy_ids'])} on the "
        "Pareto frontier before selecting."
    )
    st.json(receipt["dfcm"]["selected_policy"])

    st.subheader("Recommendations")
    for recommendation in receipt["recommendations"]:
        with st.expander(
            f"{recommendation['title']} — score {recommendation['score']}"
        ):
            st.write(recommendation["explanation"])
            st.json(recommendation["signals"])

    with st.expander("Candidate admission / refusal trace"):
        st.json(receipt["candidate_trace"])

    st.subheader("Replay receipt")
    st.code(receipt["receipt_id"])
    st.caption(
        f"Receipt verifies: {verify_receipt(receipt)}. Authority: "
        f"{receipt['authority']}. Actuation performed: {receipt['actuation_performed']}."
    )
