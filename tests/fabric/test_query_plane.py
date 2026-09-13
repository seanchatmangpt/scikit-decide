from autofde_lab.fabric.query_plane import PolyglotQueryPlane

RECORDS = (
    {
        "event_id": "e2",
        "case_id": "c1",
        "timestamp": "2026-08-08T00:02:00Z",
        "type": "verify",
        "standing": "ALIVE",
        "text": "verification complete",
    },
    {
        "event_id": "e1",
        "case_id": "c1",
        "timestamp": "2026-08-08T00:01:00Z",
        "type": "actuate",
        "standing": "ALIVE",
        "text": "broker occurrence",
    },
    {
        "event_id": "e3",
        "case_id": "c2",
        "timestamp": "2026-08-08T00:03:00Z",
        "type": "refusal",
        "standing": "REFUSED",
        "text": "authority refused",
    },
)


def test_same_subjects_are_queryable_through_four_views():
    plane = PolyglotQueryPlane(RECORDS)
    assert [
        row["event_id"]
        for row in plane.semantic(predicate="type", object_value="verify").rows
    ] == ["e2"]
    assert [
        row["event_id"]
        for row in plane.relational(lambda row: row["standing"] == "REFUSED").rows
    ] == ["e3"]
    assert [row["event_id"] for row in plane.search("broker").rows] == ["e1"]
    assert [row["event_id"] for row in plane.process(case_id="c1").rows] == ["e1", "e2"]


def test_query_cost_is_explicit_not_hidden():
    plane = PolyglotQueryPlane(RECORDS)
    for result in (
        plane.semantic(predicate="standing", object_value="ALIVE"),
        plane.relational(lambda _: True),
        plane.search("complete"),
        plane.process(case_id="c1"),
    ):
        assert result.examined == len(RECORDS)
