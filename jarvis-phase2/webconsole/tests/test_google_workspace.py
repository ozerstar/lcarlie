import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import google_workspace


class GoogleWorkspaceTests(unittest.TestCase):
    def test_calendar_hides_future_birthdays_but_keeps_today(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        events = [
            {"summary": "Bugünkü doğum günü", "eventType": "birthday",
             "start": {"date": today.isoformat()}},
            {"summary": "Gelecek doğum günü", "eventType": "birthday",
             "start": {"date": (today + timedelta(days=2)).isoformat()}},
            {"summary": "Toplantı", "start": {"date": (today + timedelta(days=2)).isoformat()}},
        ]
        with patch.object(google_workspace, "_calendar_items", return_value=events):
            titles = [event["title"] for event in google_workspace.calendar_events("alice")]
        self.assertEqual(titles, ["Bugünkü doğum günü", "Toplantı"])

    def test_drive_scope_allows_file_content(self):
        self.assertIn("https://www.googleapis.com/auth/drive.readonly", google_workspace.SCOPES)
        self.assertIn("https://www.googleapis.com/auth/drive.file", google_workspace.SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/drive.metadata.readonly", google_workspace.SCOPES)

    def test_drive_upload_requires_new_permission(self):
        with patch.object(google_workspace, "status", return_value={"connected": True, "drive_write": False}):
            with self.assertRaisesRegex(google_workspace.GoogleError, "yeniden bağlayıp"):
                google_workspace.prepare("alice", "drive.upload", {"attachment_id": "a" * 32})

    def test_drive_upload_requires_approval_and_preserves_original(self):
        attachment_id = "a" * 32
        payload = {"attachment_id": attachment_id, "folder_id": "", "name": "art.jpg"}
        with patch.object(google_workspace, "status", return_value={"connected": True, "drive_write": True}), \
                patch("mobile_features.attachment", return_value=({"name": "art.png", "suffix": ".jpg"}, Path(__file__))), \
                patch.object(google_workspace.action_store, "create", return_value={
                    "id": "a" * 32, "kind": "drive.upload", "description": "Drive'a kaydet",
                    "status": "AWAITING_APPROVAL", "fingerprint": "f" * 64}) as create, \
                patch.object(google_workspace.action_store, "decide", return_value=(
                    {"kind": "drive.upload"}, payload)) as decide, \
                patch.object(google_workspace.action_store, "finish") as finish, \
                patch.object(google_workspace, "_access_token", return_value="test-token"), \
                patch.object(google_workspace, "_upload_drive_attachment", return_value={"id": "drive-id"}) as upload:
            proposal = google_workspace.prepare("alice", "drive.upload", {"attachment_id": attachment_id})
            self.assertIn("Hedef klasör: Drive ana dizini", proposal["details"])
            upload.assert_not_called()
            result = google_workspace.decide("alice", proposal["id"], "APPROVED", proposal["fingerprint"])
            self.assertEqual(result["status"], "DONE")
            upload.assert_called_once_with("alice", payload, "test-token")
            self.assertEqual(create.call_args.kwargs["idempotency_key"], None)
            decide.assert_called_once_with("alice", "a" * 32, "APPROVED", "f" * 64)
            finish.assert_called_once_with("alice", "a" * 32, "COMPLETED",
                                           "Dosya Drive'a yeni kopya olarak kaydedildi.", "drive-id")

    def test_drive_upload_uses_new_file_endpoint(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, *_args):
                return b'{"id":"created"}'

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "art.jpg"
            path.write_bytes(b"image")
            with patch("mobile_features.attachment", return_value=({"kind": "image"}, path)), \
                    patch.object(google_workspace.urllib.request, "urlopen", return_value=Response()) as send:
                result = google_workspace._upload_drive_attachment("alice", {"attachment_id": "a" * 32,
                    "name": "art.jpg", "folder_id": ""}, "test-token")
            self.assertEqual(result["id"], "created")
            request = send.call_args.args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertIn("/upload/drive/v3/files?", request.full_url)
            self.assertIn(b"image", request.data)

    def test_creative_files_are_limited_to_current_image_outputs(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(google_workspace, "CREATIVE_ROOT", Path(folder)):
            current = Path(folder) / "campaign-gorseller"
            current.mkdir()
            (current / "art.jpg").write_bytes(b"image")
            archive = Path(folder) / "arsiv"
            archive.mkdir()
            (archive / "private.jpg").write_bytes(b"image")
            files = google_workspace.creative_files()
            self.assertEqual([item["id"] for item in files], ["campaign-gorseller/art.jpg"])
            self.assertEqual(files[0]["preview_url"], "/kreatif/campaign-gorseller/art.jpg")
            with self.assertRaises(google_workspace.GoogleError):
                google_workspace._creative_path("../arsiv/private.jpg")

    def test_creative_upload_rechecks_approved_content(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(google_workspace, "CREATIVE_ROOT", Path(folder)):
            current = Path(folder) / "campaign-gorseller"
            current.mkdir()
            (current / "art.jpg").write_bytes(b"changed")
            with patch.object(google_workspace.urllib.request, "urlopen") as send:
                with self.assertRaisesRegex(google_workspace.GoogleError, "onaydan sonra değişti"):
                    google_workspace._upload_drive_attachment("alice", {"creative_id": "campaign-gorseller/art.jpg",
                        "sha256": "0" * 64, "name": "art.jpg", "folder_id": ""}, "test-token")
                send.assert_not_called()

    def test_pending_creative_upload_has_preview(self):
        from datetime import datetime, timezone
        with patch.object(google_workspace.action_store, "list_visible", return_value=[{
                "action_id": "one", "kind": "drive.upload",
                "payload": {"creative_id": "campaign-gorseller/art.jpg"},
                "payload_hash": "f" * 64, "description": "Drive'a kaydet",
                "status": "AWAITING_APPROVAL", "expires_at": datetime.now(timezone.utc)}]):
            pending = google_workspace.pending_actions("alice")
            self.assertEqual(pending[0]["preview_url"], "/kreatif/campaign-gorseller/art.jpg")
            self.assertEqual(pending[0]["fingerprint"], "f" * 64)
            self.assertIn("Hedef klasör: Drive ana dizini", pending[0]["details"])

    def test_calendar_approval_shows_start_and_end(self):
        details = google_workspace._approval_details("calendar.create", {
            "summary": "Toplantı", "start": {"dateTime": "2030-01-01T09:00:00+03:00"},
            "end": {"dateTime": "2030-01-01T10:00:00+03:00"}}, "")
        self.assertIn("Başlangıç:", details)
        self.assertIn("Bitiş:", details)

    def test_stale_approval_cannot_reach_google(self):
        with patch.object(google_workspace.action_store, "decide",
                          side_effect=google_workspace.action_store.ActionConflict(
                              "İşlem ayrıntıları değişmiş.")), \
                patch.object(google_workspace, "_access_token") as token:
            with self.assertRaises(google_workspace.GoogleError):
                google_workspace.decide("alice", "a" * 32, "APPROVED", "wrong")
            token.assert_not_called()

    def test_invalid_identifier_is_rejected_without_network(self):
        with patch.object(google_workspace, "_access_token") as token:
            with self.assertRaises(google_workspace.GoogleError):
                google_workspace.import_drive_file("alice", "../invalid")
            token.assert_not_called()

    def test_large_file_is_rejected_before_download(self):
        metadata = {"name": "big.pdf", "mimeType": "application/pdf", "size": "5242881"}
        with patch.object(google_workspace, "_access_token", return_value="test-token"), \
                patch.object(google_workspace, "_http_json", return_value=metadata), \
                patch.object(google_workspace.urllib.request, "urlopen") as download:
            with self.assertRaisesRegex(google_workspace.GoogleError, "5 MB"):
                google_workspace.import_drive_file("alice", "1234567890")
            download.assert_not_called()

    def test_google_document_is_exported_and_uploaded_to_owner(self):
        metadata = {"name": "Notlar", "mimeType": "application/vnd.google-apps.document"}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, limit):
                self.limit = limit
                return b"test content"

        response = Response()
        with patch.object(google_workspace, "_access_token", return_value="test-token"), \
                patch.object(google_workspace, "_http_json", return_value=metadata), \
                patch.object(google_workspace.urllib.request, "urlopen", return_value=response) as download, \
                patch("mobile_features.upload", return_value={"id": "attached"}) as upload:
            result = google_workspace.import_drive_file("alice", "1234567890")
        self.assertEqual(result["id"], "attached")
        upload.assert_called_once_with("alice", "Notlar.txt", b"test content")
        self.assertIn("/export?mimeType=text%2Fplain", download.call_args.args[0].full_url)


if __name__ == "__main__":
    unittest.main()
