"""Guarded Wix Catalog V1 image publisher. Requires reviewed one-to-one mapping.

No automatic retry: Wix writes are not transactionally atomic. A failure leaves a
per-product journal and PUBLISH_FAILED state for deliberate inspection.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

from jarvis.image_jobs import ImageJobs, SLOTS

BASE = "https://www.wixapis.com"
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}$")


def validate_mapping(job: dict, mapping: dict) -> None:
    folders = set(job["report"].get("products") or {})
    if not folders or folders != set(mapping):
        raise ValueError("Ürün eşlemesi paketteki tüm klasörleri bire bir kapsamalı.")
    ids = []
    for folder, item in mapping.items():
        if not isinstance(item, dict) or not UUID.fullmatch(str(item.get("id", ""))):
            raise ValueError(f"{folder}: Wix ürün ID eksik/geçersiz.")
        if not str(item.get("slug", "")).strip():
            raise ValueError(f"{folder}: canlı ürün slug doğrulaması gerekli.")
        ids.append(item["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Bir Wix ürünü birden fazla klasöre eşlenmiş.")


def validate_media_stage(job: dict, stage: dict, site_id: str) -> dict[tuple[str, str], str]:
    if not isinstance(stage, dict) or stage.get("jobId") != job["id"] or stage.get("siteId") != site_id:
        raise ValueError("Medya hazırlığı iş veya Wix sitesi ile eşleşmiyor.")
    expected = {(folder, slot) for folder in job["report"].get("products", {}) for slot in SLOTS}
    staged: dict[tuple[str, str], str] = {}
    for item in stage.get("items") or []:
        key = (item.get("product"), item.get("slot"))
        media_id = str(item.get("mediaId") or "")
        if key not in expected or key in staged or not item.get("success") or not media_id:
            raise ValueError("Medya hazırlığında eksik, yinelenen veya başarısız dosya var.")
        if not media_id.endswith("~mv2.jpg"):
            raise ValueError("Wix medya ID biçimi geçersiz.")
        staged[key] = media_id
    if set(staged) != expected or len(set(staged.values())) != len(expected):
        raise ValueError("Medya hazırlığı 195 görseli bire bir kapsamıyor.")
    return staged


def _media_ids(product: dict) -> list[str]:
    return [str(item.get("id") or item.get("mediaId") or "")
            for item in ((product.get("media") or {}).get("items") or [])]


class WixClient:
    def __init__(self, api_key: str, site_id: str, timeout: int = 30):
        if not api_key or not site_id:
            raise ValueError("WIX_API_KEY ve WIX_SITE_ID gerekli.")
        self.api_key, self.site_id, self.timeout = api_key, site_id, timeout

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(BASE + path, data=data, method=method,
            headers={"Authorization": self.api_key, "wix-site-id": self.site_id,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as res:
            raw = res.read()
        return json.loads(raw) if raw else {}

    def product(self, product_id: str) -> dict:
        return self.call("GET", f"/stores/v1/products/{product_id}")["product"]

    def media_ready(self, media_id: str) -> bool:
        detail = self.call("GET", "/site-media/v1/files/get-file-by-id?" +
                           urllib.parse.urlencode({"fileId": media_id}))
        file = detail.get("file") or {}
        return file.get("id") == media_id and file.get("operationStatus") == "READY" and file.get("state") == "OK"

    def upload(self, filename: str, content: bytes) -> str:
        ticket = self.call("POST", "/site-media/v1/files/generate-upload-url",
                           {"mimeType": "image/jpeg", "fileName": filename})
        url = ticket["uploadUrl"]
        if urllib.parse.urlparse(url).scheme != "https":
            raise ValueError("Wix yükleme URL'si HTTPS değil.")
        request = urllib.request.Request(url, data=content, method="PUT",
                                         headers={"Content-Type": "image/jpeg"})
        with urllib.request.urlopen(request, timeout=self.timeout) as res:
            uploaded = json.loads(res.read())
        file_id = str(uploaded["file"]["id"])
        for _ in range(20):
            detail = self.call("GET", "/site-media/v1/files/get-file-by-id?" +
                               urllib.parse.urlencode({"fileId": file_id}))
            state = str((detail.get("file") or {}).get("state") or "")
            if state == "READY":
                return file_id
            if state == "FAILED":
                raise RuntimeError(f"Wix medya işleme başarısız: {filename}")
            time.sleep(3)
        raise TimeoutError(f"Wix medya hazır olmadı: {filename}")

    def add(self, product_id: str, media_ids: list[str]) -> None:
        self.call("POST", f"/stores/v1/products/{product_id}/media",
                  {"media": [{"mediaId": i} for i in media_ids]})

    def remove(self, product_id: str, media_ids: list[str]) -> None:
        if media_ids:
            self.call("POST", f"/stores/v1/products/{product_id}/media/delete",
                      {"mediaIds": media_ids})


def publish(job_id: str, mapping: dict, jobs: ImageJobs, client: WixClient,
            media_stage: dict | None = None) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise ValueError("İş bulunamadı.")
    validate_mapping(job, mapping)
    staged = validate_media_stage(job, media_stage, client.site_id) if media_stage is not None else None
    # Persist review gate before any external write.
    jobs.begin_publish(job_id)
    journal = jobs.root / (job_id + "-publish.jsonl")

    def record(folder: str, stage: str, **fields):
        with journal.open("a", encoding="utf-8") as out:
            out.write(json.dumps({"at": time.time(), "folder": folder, "stage": stage,
                                  **fields}, ensure_ascii=False) + "\n")

    try:
        for folder in sorted(mapping):
            item = mapping[folder]
            product_id = item["id"]
            before = client.product(product_id)
            if before.get("slug") != item["slug"]:
                raise ValueError(f"{folder}: canlı Wix slug değişmiş; yayın durdu.")
            old_ids = [x for x in _media_ids(before) if x]
            record(folder, "BACKUP", product_id=product_id, slug=before.get("slug"), old_media_ids=old_ids)
            new_ids = []
            added, old_removed = False, False
            try:
                for slot in SLOTS:
                    if staged is None:
                        content = jobs.member(job_id, folder, slot)
                        new_ids.append(client.upload(f"lcarlie-{folder}-{slot}", content))
                    else:
                        media_id = staged[(folder, slot)]
                        if not client.media_ready(media_id):
                            raise RuntimeError(f"{folder}/{slot}: Wix medyası henüz hazır değil.")
                        new_ids.append(media_id)
                record(folder, "UPLOADED", new_media_ids=new_ids)
                client.add(product_id, new_ids)
                added = True
                present = _media_ids(client.product(product_id))
                if not set(new_ids).issubset(present):
                    raise RuntimeError(f"{folder}: yeni medya Wix üründe doğrulanamadı.")
                record(folder, "ADDED")
                client.remove(product_id, old_ids)
                old_removed = bool(old_ids)
                after = client.product(product_id)
                actual = _media_ids(after)
                main = ((after.get("media") or {}).get("mainMedia") or {}).get("id")
                if set(actual) != set(new_ids) or main != new_ids[0]:
                    record(folder, "VERIFY_FAILED", actual_media_ids=actual, main_media_id=main)
                    raise RuntimeError(f"{folder}: yeni medya sırası/doğrulaması başarısız.")
                record(folder, "VERIFIED", main_media_id=main)
            except Exception:
                try:
                    if old_removed:
                        client.add(product_id, old_ids)
                        record(folder, "RESTORED_OLD")
                    elif added:
                        client.remove(product_id, new_ids)
                        record(folder, "REMOVED_NEW")
                except Exception as rollback_error:  # noqa: BLE001 - tek is coktugunde kuyruk durmaz; hata kayda gecer
                    record(folder, "ROLLBACK_FAILED", error=str(rollback_error)[:300])
                raise
    except Exception as exc:
        jobs.finish_publish(job_id, str(exc))
        raise
    return jobs.finish_publish(job_id)
