from rca.rag import _filter_by_distance, _historical_date_filter


def test_historical_date_filter_uses_collection_metadata_field():
    assert _historical_date_filter("historical_rcas", 100) == {"completion_date": {"$lt": 100}}
    assert _historical_date_filter("historical_incidents", 100) == {"detected_at": {"$lt": 100}}


def test_distance_filter_drops_weak_matches_and_preserves_result_shape():
    results = {
        "ids": [["strong", "weak"]],
        "documents": [["useful", "irrelevant"]],
        "distances": [[0.2, 0.8]],
    }

    filtered = _filter_by_distance(results, max_distance=0.45, limit=5)

    assert filtered["ids"] == [["strong"]]
    assert filtered["documents"] == [["useful"]]
    assert filtered["distances"] == [[0.2]]