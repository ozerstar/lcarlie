"""The office must distinguish current work from historical cycle results."""
from datetime import datetime, timedelta, timezone

from jarvis import office_events, roster


def test_member_events_are_bounded_and_terminal_event_clears_active(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    office_events.emit("member", member_key="web_gelistirici", status="WORKING",
                       task="X" * 300)
    first = office_events.recent()
    assert len(first) == 1
    assert len(first[0]["task"]) == office_events.MAX_FIELD
    assert "web_gelistirici" in office_events.active_members()

    office_events.emit("member", member_key="web_gelistirici", status="COMPLETED")
    assert "web_gelistirici" not in office_events.active_members()


def test_stale_work_does_not_look_live(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    office_events.emit("member", member_key="seo_icerik", status="WORKING")
    later = datetime.now(timezone.utc) + timedelta(minutes=11)
    assert office_events.active_members(now=later) == {}


def test_roster_callback_tracks_each_member_without_changing_results():
    class EmptyMemory:
        def _fetch(self, _query):
            return type("Evidence", (), {"records": [], "source": "", "authority": ""})()

    sequence = []
    rows = roster.opinions(
        EmptyMemory(), only=("web_gelistirici", "seo_icerik"),
        on_member_start=lambda member: sequence.append(("start", member.key)),
        on_member_done=lambda row: sequence.append(("done", row["key"])))
    assert len(rows) == 2
    assert sequence == [
        ("start", "web_gelistirici"), ("done", "web_gelistirici"),
        ("start", "seo_icerik"), ("done", "seo_icerik")]
