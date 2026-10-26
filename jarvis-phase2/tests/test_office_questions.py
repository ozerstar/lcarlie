"""Manager status questions must reflect measured work without inventing idleness."""
from jarvis.office_questions import activity_evidence


def test_activity_evidence_separates_live_work_from_last_measurement():
    report = {"generated_at": "2026-10-26T03:00:00+00:00", "activity": {
        "manager": {"status": "WAITING", "task": "Kaynakları oku",
                    "result": "Girdi bekleniyor", "finished_at": "2026-10-26T03:01:00+00:00"},
        "other_team": {"status": "WORKED", "task": "Başka iş"},
    }}
    active = {"manager": {"task": "Yeni raporu inceliyor"}}
    result = activity_evidence("WEB", ("manager",), report, active)
    assert result["ref"].startswith("office:team-cycle:WEB:")
    assert "Yeni raporu inceliyor" in result["summary"]
    assert "Girdi bekleniyor" in result["summary"]
    assert "Başka iş" not in result["summary"]


def test_no_live_event_is_not_called_idleness():
    report = {"generated_at": "2026-10-26T03:00:00+00:00", "activity": {}}
    result = activity_evidence("SEO", ("manager",), report, {})
    assert "boş durduğunu kanıtlamaz" in result["summary"]
    assert activity_evidence("SEO", ("manager",), {}, {}) is None
