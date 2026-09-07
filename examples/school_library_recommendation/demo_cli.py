from __future__ import annotations

import json
from pathlib import Path

from llm import parse_librarian_request
from recommender import HybridRecommender, load_data


def main() -> None:
    data_dir = Path(__file__).parent / "data"
    catalog, circulation = load_data(data_dir)
    recommender = HybridRecommender(catalog, circulation)

    student_id = "S104"
    request = "Something funny, preferably a mystery, and not part of a long series."
    intent = parse_librarian_request(request)
    recommendations = recommender.recommend(student_id, intent, top_k=5)

    receipt = {
        "student_id": student_id,
        "request": request,
        "structured_intent": intent.__dict__,
        "recommendations": [r.__dict__ for r in recommendations],
        "llm_changed_ranking": False,
        "llm_supplied_facts": False,
        "demo_data": "synthetic",
    }
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
