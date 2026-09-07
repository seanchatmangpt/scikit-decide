from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import parse_librarian_request
from recommender import HybridRecommender, load_data

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_recommendations_exclude_recently_borrowed_books():
    catalog, circulation = load_data(DATA_DIR)
    recommender = HybridRecommender(catalog, circulation)
    intent = parse_librarian_request("funny mystery")
    borrowed = set(recommender.borrowed_books("S104"))
    recs = recommender.recommend("S104", intent, top_k=5)
    assert recs
    assert all(r.book_id not in borrowed for r in recs)


def test_librarian_request_becomes_structured_constraints():
    intent = parse_librarian_request("Something funny, preferably a mystery, and not part of a long series.")
    assert "humor" in intent.themes
    assert "mystery" in intent.themes
    assert intent.avoid_long_series is True


def test_receipt_signals_are_present():
    catalog, circulation = load_data(DATA_DIR)
    recommender = HybridRecommender(catalog, circulation)
    rec = recommender.recommend("S104", parse_librarian_request("funny mystery"), top_k=1)[0]
    assert {"content_similarity", "co_circulation", "intent_match", "available"}.issubset(rec.signals)
