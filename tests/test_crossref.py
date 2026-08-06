from __future__ import annotations

from types import SimpleNamespace

import ingestion.crossref as crossref


def test_parse_crossref_filters_records_without_title_or_summary() -> None:
    payload = {
        "message": {
            "items": [
                {"DOI": "10.1/valid", "title": ["<b>Valid</b>"], "abstract": "<jats:p>Useful text.</jats:p>"},
                {"DOI": "10.1/missing-summary", "title": ["Ignored"]},
                {"DOI": "10.1/missing-title", "abstract": "Ignored"},
            ]
        }
    }
    records = crossref.parse_crossref_payload(payload)
    assert len(records) == 1
    assert records[0].title == "Valid"
    assert records[0].summary == "Useful text."


def test_request_retries_503(monkeypatch) -> None:
    payload = {"message": {"items": []}}
    responses = [
        SimpleNamespace(status_code=503, headers={}, raise_for_status=lambda: (_ for _ in ()).throw(Exception("503"))),
        SimpleNamespace(status_code=200, headers={}, raise_for_status=lambda: None, json=lambda: payload),
    ]
    monkeypatch.setattr(crossref.requests, "get", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(crossref.time, "sleep", lambda _: None)
    response = crossref._request_crossref({"query.bibliographic": "machine learning"})
    assert response.status_code == 200
