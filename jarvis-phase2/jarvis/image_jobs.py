"""Durable, evidence-backed image pack jobs. No website mutation happens here."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
import zipfile
from contextlib import closing, contextmanager
from pathlib import Path

MAX_UPLOAD = 110 * 1024 * 1024
MAX_UNCOMPRESSED = 500 * 1024 * 1024
SLOTS = ("01-KAPAK.jpg", "02-FAYDA.jpg", "03-ICERIK.jpg", "04-KULLANIM.jpg", "05-RUTIN.jpg")
PRODUCT = re.compile(r"^E-TICARET/([0-9]{2})-([a-z0-9-]+)/([0-9]{2}-[A-Z]+\.jpg)$")


class ImageJobs:
    def __init__(self, state_dir: Path):
        self.root = Path(state_dir) / "image-jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "jobs.sqlite3"
        with self._connect() as cx:
            cx.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, filename TEXT NOT NULL,
                sha256 TEXT NOT NULL, report TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '')""")
            cx.execute("""CREATE TABLE IF NOT EXISTS reviews (
                job_id TEXT NOT NULL, department TEXT NOT NULL, reviewer TEXT NOT NULL,
                decision TEXT NOT NULL, comment TEXT NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(job_id, department), FOREIGN KEY(job_id) REFERENCES jobs(id))""")
            cx.execute("""CREATE TABLE IF NOT EXISTS team_notes (
                job_id TEXT NOT NULL, department TEXT NOT NULL, status TEXT NOT NULL,
                comment TEXT NOT NULL, error TEXT NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(job_id, department), FOREIGN KEY(job_id) REFERENCES jobs(id))""")

    @contextmanager
    def _connect(self):
        cx = sqlite3.connect(self.db, timeout=20)
        cx.row_factory = sqlite3.Row
        try:
            with cx:
                yield cx
        finally:
            cx.close()

    def create_from_stream(self, stream, length: int, filename: str, owner: str) -> dict:
        if length < 1 or length > MAX_UPLOAD:
            raise ValueError("ZIP boyutu sınır dışında (en çok 110 MB).")
        if not filename.lower().endswith(".zip"):
            raise ValueError("Yalnız ZIP dosyası kabul edilir.")
        job_id = uuid.uuid4().hex
        path = self.root / (job_id + ".zip")
        digest = hashlib.sha256()
        try:
            with path.open("xb") as out:
                os.chmod(path, 0o600)
                remaining = length
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Yükleme tamamlanmadı.")
                    out.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            if not zipfile.is_zipfile(path):
                raise ValueError("Dosya geçerli bir ZIP değil.")
            now = time.time()
            with self._connect() as cx:
                cx.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                           (job_id, owner, "QUEUED", now, now, Path(filename).name[:180],
                            digest.hexdigest(), "{}", ""))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._connect() as cx:
            row = cx.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            reviews = [dict(r) for r in cx.execute(
                "SELECT department,reviewer,decision,comment,created FROM reviews WHERE job_id=? ORDER BY department", (job_id,))]
            notes = [dict(r) for r in cx.execute(
                "SELECT department,status,comment,error,created FROM team_notes WHERE job_id=? ORDER BY department", (job_id,))]
        result = dict(row)
        result["report"] = json.loads(result["report"])
        result["reviews"] = reviews
        result["team_notes"] = notes
        result["visual_review"] = self.visual_review_summary(job_id)
        result["media_stage"] = self.media_stage_summary(job_id)
        return result

    def media_stage_summary(self, job_id: str) -> dict:
        path = self.root / (job_id + "-media-stage.json")
        if not path.exists():
            return {"uploaded": 0, "ready": 0, "total": 0, "complete": False}
        try:
            stage = json.loads(path.read_text(encoding="utf-8"))
            items = stage["items"]
            ids = [x["mediaId"] for x in items if x.get("success") and x.get("mediaId")]
            ready = sum(bool(x.get("verifiedReady")) for x in items)
            complete = (stage.get("jobId") == job_id and len(items) == 195 and
                        len(ids) == 195 and len(set(ids)) == 195)
            return {"uploaded": len(ids), "ready": ready, "total": len(items), "complete": complete}
        except (OSError, ValueError, KeyError, TypeError):
            return {"uploaded": 0, "ready": 0, "total": 0, "complete": False}

    def visual_review_summary(self, job_id: str) -> dict:
        """Read progress from the separate vision worker without trusting partial results."""
        db = self.root / "visual-reviews.sqlite3"
        if not db.exists():
            return {"done": 0, "failed": 0, "total": 0, "complete": False, "decision_ready": False}
        with closing(sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)) as cx:
            counts = dict(cx.execute("SELECT status,count(*) FROM observations WHERE job_id=? GROUP BY status",
                                     (job_id,)).fetchall())
        total = sum(counts.values())
        return {"done": counts.get("DONE", 0), "failed": counts.get("FAILED", 0),
                "total": total, "complete": counts.get("DONE", 0) == 195 and not counts.get("FAILED", 0),
                "decision_ready": (self.root / (job_id + "-decision.md")).exists()}

    def visual_observations(self, job_id: str) -> dict:
        job = self.get(job_id)
        if not job:
            raise ValueError("İş bulunamadı.")
        db = self.root / "visual-reviews.sqlite3"
        observations = {}
        if db.exists():
            with closing(sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)) as cx:
                cx.row_factory = sqlite3.Row
                for row in cx.execute("SELECT product,slot,status,result,error FROM observations WHERE job_id=? ORDER BY product,slot", (job_id,)):
                    observations[f"{row['product']}/{row['slot']}"] = {
                        "status": row["status"], "result": json.loads(row["result"]), "error": row["error"]}
        return {"summary": job["visual_review"], "observations": observations}

    def visual_report(self, job_id: str) -> bytes:
        if not self.get(job_id):
            raise ValueError("İş bulunamadı.")
        path = self.root / (job_id + "-visual-review.md")
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise ValueError("Tam inceleme raporu henüz hazır değil.") from None

    def visual_decision(self, job_id: str) -> bytes:
        if not self.get(job_id):
            raise ValueError("İş bulunamadı.")
        path = self.root / (job_id + "-decision.md")
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise ValueError("Doğrulanmış karar henüz hazır değil.") from None

    def save_team_note(self, job_id: str, department: str, response: dict) -> dict:
        if department not in ("WEB", "TASARIM") or not self.get(job_id):
            raise ValueError("Geçersiz iş veya departman.")
        comment = str(response.get("cevap") or "")[:6000]
        unverified = response.get("dogrulanmayan_sayilar") or []
        ok = bool(response.get("model_kullanildi") and comment and not response.get("hata") and not unverified)
        error = "" if ok else str(response.get("hata") or
                                   (f"Doğrulanmayan sayılar: {unverified}" if unverified else "") or
                                   response.get("cevap") or "Ekip yanıtı alınamadı.")[:500]
        with self._connect() as cx:
            cx.execute("INSERT INTO team_notes VALUES (?,?,?,?,?,?) ON CONFLICT(job_id,department) DO UPDATE SET "
                       "status=excluded.status,comment=excluded.comment,error=excluded.error,created=excluded.created",
                       (job_id, department, "DONE" if ok else "BLOCKED", comment if ok else "", error, time.time()))
        return self.get(job_id)

    def begin_team_note(self, job_id: str, department: str) -> None:
        if department not in ("WEB", "TASARIM") or not self.get(job_id):
            raise ValueError("Geçersiz iş veya departman.")
        now = time.time()
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT status,created FROM team_notes WHERE job_id=? AND department=?",
                             (job_id, department)).fetchone()
            if row and row["status"] == "RUNNING" and now - row["created"] < 600:
                raise ValueError("Ekip görüşü zaten hazırlanıyor.")
            cx.execute("INSERT INTO team_notes VALUES (?,?,?,?,?,?) ON CONFLICT(job_id,department) DO UPDATE SET "
                       "status='RUNNING',comment='',error='',created=excluded.created",
                       (job_id, department, "RUNNING", "", "", now))

    def list(self, limit: int = 30) -> list[dict]:
        with self._connect() as cx:
            ids = [r[0] for r in cx.execute("SELECT id FROM jobs ORDER BY created DESC LIMIT ?", (min(max(limit, 1), 100),))]
        return [self.get(i) for i in ids]

    def run_next(self) -> dict | None:
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT id FROM jobs WHERE status='QUEUED' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            job_id = row[0]
            cx.execute("UPDATE jobs SET status='RUNNING',updated=? WHERE id=?", (time.time(), job_id))
        try:
            report = self._inspect(self.root / (job_id + ".zip"))
            status, error = "REVIEW_PENDING", ""
        except Exception as exc:  # noqa: BLE001 - tek is coktugunde kuyruk durmaz; hata kayda gecer
            report, status, error = {}, "FAILED", str(exc)[:500]
        with self._connect() as cx:
            cx.execute("UPDATE jobs SET status=?,report=?,error=?,updated=? WHERE id=? AND status='RUNNING'",
                       (status, json.dumps(report, ensure_ascii=False), error, time.time(), job_id))
        return self.get(job_id)

    def recover(self, stale_seconds: int = 600) -> int:
        """A crashed worker is visible and retryable; it never becomes completed."""
        with self._connect() as cx:
            cur = cx.execute("UPDATE jobs SET status='FAILED',error='İşçi kesildi; yeniden kuyruğa alınmalı.',updated=? "
                             "WHERE status='RUNNING' AND updated<?", (time.time(), time.time()-stale_seconds))
            notes = cx.execute("UPDATE team_notes SET status='BLOCKED',error='Ekip görüşü yarıda kaldı; yeniden isteyin.' "
                               "WHERE status='RUNNING' AND created<?", (time.time()-stale_seconds,))
            return cur.rowcount + notes.rowcount

    def begin_publish(self, job_id: str) -> dict:
        job = self.get(job_id)
        if not job or job["status"] != "READY_FOR_OWNER" or not job["report"].get("structural_pass"):
            raise ValueError("İş, görsel yayın aşamasına hazır değil.")
        if not job["visual_review"]["complete"]:
            raise ValueError("195 görselin içerik incelemesi tamamlanmadan yayın başlatılamaz.")
        reviews = {r["department"]: r["decision"] for r in job["reviews"]}
        if reviews != {"WEB": "APPROVE", "TASARIM": "APPROVE"}:
            raise ValueError("WEB ve TASARIM insan onayları gerekli.")
        with self._connect() as cx:
            cur = cx.execute("UPDATE jobs SET status='PUBLISHING',updated=? WHERE id=? AND status='READY_FOR_OWNER'",
                             (time.time(), job_id))
            if cur.rowcount != 1:
                raise ValueError("Yayın işlemi zaten başlatılmış.")
        return self.get(job_id)

    def finish_publish(self, job_id: str, error: str = "") -> dict:
        with self._connect() as cx:
            cur = cx.execute("UPDATE jobs SET status=?,error=?,updated=? WHERE id=? AND status='PUBLISHING'",
                             ("PUBLISH_FAILED" if error else "PUBLISHED", error[:500], time.time(), job_id))
            if cur.rowcount != 1:
                raise ValueError("Yayın durum geçişi geçersiz.")
        return self.get(job_id)

    def retry(self, job_id: str) -> dict:
        with self._connect() as cx:
            cur = cx.execute("UPDATE jobs SET status='QUEUED',error='',updated=? WHERE id=? AND status='FAILED'",
                             (time.time(), job_id))
            if cur.rowcount != 1:
                raise ValueError("Yalnız başarısız iş yeniden denenebilir.")
        return self.get(job_id)

    def review(self, job_id: str, department: str, reviewer: str, decision: str, comment: str) -> dict:
        if department not in ("WEB", "TASARIM") or decision not in ("APPROVE", "CHANGES_REQUIRED"):
            raise ValueError("Geçersiz departman veya karar.")
        if len(comment.strip()) < 10 or len(comment) > 3000:
            raise ValueError("Gerekçeli yorum 10-3000 karakter olmalı.")
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT status,report FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or row[0] not in ("REVIEW_PENDING", "CHANGES_REQUIRED", "READY_FOR_OWNER"):
                raise ValueError("İş inceleme aşamasında değil.")
            if decision == "APPROVE" and not json.loads(row["report"]).get("structural_pass"):
                raise ValueError("Yapısal hatalı paket onaylanamaz.")
            cx.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?) ON CONFLICT(job_id,department) DO UPDATE SET "
                       "reviewer=excluded.reviewer,decision=excluded.decision,comment=excluded.comment,created=excluded.created",
                       (job_id, department, reviewer, decision, comment.strip(), time.time()))
            decisions = [r[0] for r in cx.execute("SELECT decision FROM reviews WHERE job_id=?", (job_id,))]
            status = ("CHANGES_REQUIRED" if "CHANGES_REQUIRED" in decisions else
                      "READY_FOR_OWNER" if len(decisions) == 2 and all(d == "APPROVE" for d in decisions) else
                      "REVIEW_PENDING")
            cx.execute("UPDATE jobs SET status=?,updated=? WHERE id=?", (status, time.time(), job_id))
        return self.get(job_id)

    def member(self, job_id: str, product: str, slot: str) -> bytes:
        if not re.fullmatch(r"[0-9]{2}-[a-z0-9-]+", product) or slot not in SLOTS:
            raise ValueError("Geçersiz görsel yolu.")
        if not self.get(job_id):
            raise ValueError("İş bulunamadı.")
        with zipfile.ZipFile(self.root / (job_id + ".zip")) as z:
            name = f"E-TICARET/{product}/{slot}"
            info = z.getinfo(name)
            if info.file_size > 10 * 1024 * 1024:
                raise ValueError("Görsel çok büyük.")
            return z.read(info)

    @staticmethod
    def _inspect(path: Path) -> dict:
        products: dict[str, dict] = {}
        problems: list[str] = []
        with zipfile.ZipFile(path) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            if len(infos) > 250 or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
                raise ValueError("ZIP içeriği sınırı aşıyor.")
            for info in infos:
                match = PRODUCT.fullmatch(info.filename)
                if not match:
                    if info.filename in ("BASLANGIC.txt", "URUN-ICERIK-SAYIMLARI.md"):
                        continue
                    problems.append(f"Beklenmeyen dosya: {info.filename[:120]}")
                    continue
                _, slug, slot = match.groups()
                key = match.group(1) + "-" + slug
                if slot not in SLOTS:
                    problems.append(f"Beklenmeyen görsel sırası: {info.filename}")
                    continue
                # Reading every image verifies CRC and catches truncated ZIP members.
                data = z.read(info)
                if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                    problems.append(f"JPEG işaretleri geçersiz: {info.filename}")
                products.setdefault(key, {})[slot] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for key, slots in products.items():
                missing = set(SLOTS) - set(slots)
                if missing:
                    problems.append(f"{key}: eksik {', '.join(sorted(missing))}")
        if len(products) != 39:
            problems.append(f"Ürün sayısı {len(products)}; beklenen 39.")
        return {"product_count": len(products), "image_count": sum(map(len, products.values())),
                "products": products, "problems": problems, "structural_pass": not problems,
                "review_note": "Yapısal kontrol görsel içerik ve ürün iddiası onayı değildir."}
