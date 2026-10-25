import io
import sqlite3
from contextlib import closing
import tempfile
import unittest
import zipfile
from pathlib import Path

from jarvis.image_jobs import ImageJobs, SLOTS


def pack(good=True):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        count = 39 if good else 1
        for n in range(1, count + 1):
            for slot in SLOTS:
                z.writestr(f"E-TICARET/{n:02d}-urun{n}/{slot}", b"\xff\xd8jpeg\xff\xd9")
    return out.getvalue()


class ImageJobsTest(unittest.TestCase):
    def test_durable_review_and_no_false_completion(self):
        with tempfile.TemporaryDirectory() as d:
            jobs = ImageJobs(Path(d))
            raw = pack()
            job = jobs.create_from_stream(io.BytesIO(raw), len(raw), "images.zip", "owner")
            self.assertEqual("QUEUED", job["status"])
            finished = ImageJobs(Path(d)).run_next()
            self.assertEqual("REVIEW_PENDING", finished["status"])
            self.assertEqual(195, finished["report"]["image_count"])
            self.assertEqual(b"\xff\xd8jpeg\xff\xd9", jobs.member(job["id"], "01-urun1", SLOTS[0]))
            self.assertEqual("REVIEW_PENDING", jobs.review(job["id"], "WEB", "reviewer", "APPROVE", "Ürün eşleşmeleri doğru.")["status"])
            with self.assertRaises(ValueError):
                jobs.begin_publish(job["id"])
            jobs.begin_team_note(job["id"], "WEB")
            with self.assertRaises(ValueError):
                jobs.begin_team_note(job["id"], "WEB")
            note = jobs.save_team_note(job["id"], "WEB", {"model_kullanildi": True, "cevap": "Görsel içerik ayrıca incelenmeli."})
            self.assertEqual("DONE", note["team_notes"][0]["status"])
            self.assertEqual("READY_FOR_OWNER", jobs.review(job["id"], "TASARIM", "reviewer", "APPROVE", "Yerleşim ve metinler uygun.")["status"])
            with self.assertRaisesRegex(ValueError, "195 görselin içerik incelemesi"):
                jobs.begin_publish(job["id"])
            with closing(sqlite3.connect(jobs.root / "visual-reviews.sqlite3")) as cx:
                with cx:
                    cx.execute("CREATE TABLE observations (job_id TEXT, product TEXT, slot TEXT, status TEXT)")
                    cx.executemany("INSERT INTO observations VALUES (?,?,?,?)",
                                   ((job["id"], f"{n:02d}-urun{n}", slot, "DONE")
                                    for n in range(1, 40) for slot in SLOTS))
            self.assertEqual("PUBLISHING", jobs.begin_publish(job["id"])["status"])
            self.assertEqual("PUBLISHED", jobs.finish_publish(job["id"])["status"])
            self.assertIsNone(jobs.run_next())

    def test_bad_pack_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as d:
            jobs = ImageJobs(Path(d))
            raw = pack(False)
            job = jobs.create_from_stream(io.BytesIO(raw), len(raw), "bad.zip", "owner")
            self.assertFalse(jobs.run_next()["report"]["structural_pass"])
            note = jobs.save_team_note(job["id"], "WEB", {"hata": "model unavailable"})
            self.assertEqual("BLOCKED", note["team_notes"][0]["status"])
            with self.assertRaises(ValueError):
                jobs.review(job["id"], "WEB", "r", "APPROVE", "Paket uygun görünüyor")

    def test_partial_upload_does_not_enqueue(self):
        with tempfile.TemporaryDirectory() as d:
            jobs = ImageJobs(Path(d))
            with self.assertRaises(ValueError):
                jobs.create_from_stream(io.BytesIO(b"abc"), 5, "part.zip", "owner")
            self.assertEqual([], jobs.list())


if __name__ == "__main__":
    unittest.main()
