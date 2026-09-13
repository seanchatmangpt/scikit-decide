from __future__ import annotations

import json
from pathlib import Path

from dfcm import execute_dfcm
from llm import parse_librarian_request
from recommender import load_data


def main() -> None:
    data_dir = Path(__file__).parent / "data"
    catalog, circulation = load_data(data_dir)

    student_id = "S104"
    request = "Something funny, preferably a mystery, and not part of a long series."
    intent = parse_librarian_request(request)
    receipt = execute_dfcm(
        catalog=catalog,
        circulation=circulation,
        student_id=student_id,
        raw_request=request,
        intent=intent,
        top_k=5,
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
