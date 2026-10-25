import tempfile
import unittest
from pathlib import Path

from jarvis.wix_image_publish import publish, validate_mapping, validate_media_stage
from jarvis.image_jobs import SLOTS


PRODUCT_ID = "12345678-1234-1234-1234-123456789012"
JOB = {"id": "a" * 32, "status": "READY_FOR_OWNER",
       "report": {"products": {"01-urun": {}}, "structural_pass": True},
       "reviews": [{"department": "WEB", "decision": "APPROVE"},
                   {"department": "TASARIM", "decision": "APPROVE"}]}
MAPPING = {"01-urun": {"id": PRODUCT_ID, "slug": "urun"}}


class FakeJobs:
    def __init__(self, root):
        self.root = root
        self.status = "READY_FOR_OWNER"

    def get(self, _):
        return {**JOB, "status": self.status}

    def begin_publish(self, _):
        self.status = "PUBLISHING"

    def finish_publish(self, _, error=""):
        self.status = "PUBLISH_FAILED" if error else "PUBLISHED"
        return self.get(None)

    def member(self, *_):
        return b"jpeg"


class FakeClient:
    def __init__(self, wrong_main=False):
        self.ids = ["old.jpg"]
        self.wrong_main = wrong_main
        self.site_id = "site-a"
        self.upload_calls = 0

    def product(self, _):
        return {"slug": "urun", "media": {"items": [{"id": x} for x in self.ids],
                                           "mainMedia": {"id": "wrong.jpg" if self.wrong_main else self.ids[0]}}}

    def upload(self, filename, _):
        self.upload_calls += 1
        return filename

    def media_ready(self, _):
        return True

    def add(self, _, ids):
        self.ids.extend(ids)

    def remove(self, _, ids):
        self.ids = [x for x in self.ids if x not in ids]


class PublisherTest(unittest.TestCase):
    def test_mapping_rejects_missing_or_duplicate_products(self):
        with self.assertRaises(ValueError):
            validate_mapping(JOB, {})
        with self.assertRaises(ValueError):
            validate_mapping(JOB, {"01-urun": {"id": PRODUCT_ID, "slug": ""}})

    def test_verified_replace(self):
        with tempfile.TemporaryDirectory() as d:
            jobs, client = FakeJobs(Path(d)), FakeClient()
            result = publish(JOB["id"], MAPPING, jobs, client)
            self.assertEqual("PUBLISHED", result["status"])
            self.assertEqual(5, len(client.ids))
            self.assertNotIn("old.jpg", client.ids)

    def test_failure_restores_old_media(self):
        with tempfile.TemporaryDirectory() as d:
            jobs, client = FakeJobs(Path(d)), FakeClient(wrong_main=True)
            with self.assertRaises(RuntimeError):
                publish(JOB["id"], MAPPING, jobs, client)
            self.assertEqual("PUBLISH_FAILED", jobs.status)
            self.assertIn("old.jpg", client.ids)

    def test_staged_media_skips_duplicate_upload(self):
        stage = {"jobId": JOB["id"], "siteId": "site-a", "items": [
            {"product": "01-urun", "slot": slot, "success": True,
             "mediaId": f"test_{i}~mv2.jpg"} for i, slot in enumerate(SLOTS)]}
        self.assertEqual(5, len(validate_media_stage(JOB, stage, "site-a")))
        with self.assertRaises(ValueError):
            validate_media_stage(JOB, {**stage, "siteId": "wrong"}, "site-a")
        with tempfile.TemporaryDirectory() as d:
            jobs, client = FakeJobs(Path(d)), FakeClient()
            self.assertEqual("PUBLISHED", publish(JOB["id"], MAPPING, jobs, client, stage)["status"])
            self.assertEqual(0, client.upload_calls)


if __name__ == "__main__":
    unittest.main()
