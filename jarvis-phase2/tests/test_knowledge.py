"""Tokensiz araştırma → bilgi birikimi. Ağ yok, model yok."""
import json
import pathlib
import tempfile
import unittest
from tests import EnterContextMixin
from unittest.mock import patch

from jarvis import knowledge


def source(digest, url="https://haber.com/a", publisher="haber.com",
           snippets=("Pazar 2026'da büyüdü.",), stype="NEWS", relevance=0.8,
           injection=False):
    return {"content_hash": digest, "canonical_url": url, "publisher": publisher,
            "source_type": stype, "title": "Başlık", "evidence_snippets": list(snippets),
            "observed_at": "2026-09-01", "relevance": relevance,
            "injection_detected": injection}


class FakeController:
    def __init__(self, by_topic):
        self.by_topic = by_topic
        self.calls = []

    def run(self, topic, *args, **kwargs):
        self.calls.append(topic)
        payload = self.by_topic.get(topic)
        if isinstance(payload, Exception):
            raise payload
        return payload or {"sources": [], "stop_reason": "NO_RESULTS", "model_calls": 0}


class TemelTests(EnterContextMixin, unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.enterContext(patch.object(knowledge, "STATE_DIR", tmp))
        self.enterContext(patch.object(knowledge, "KNOWLEDGE_LOG", tmp / "knowledge.jsonl"))
        self.enterContext(patch.object(knowledge, "TOPICS_FILE", tmp / "topics.json"))
        self.tmp = tmp

    def test_yeni_bulgular_kaydedilir(self):
        controller = FakeController({"konu": {"sources": [source("h1"), source("h2")],
                                              "stop_reason": "SUFFICIENT_CONFIDENCE"}})
        out = knowledge.run(controller, topics=("konu",))
        self.assertEqual(out["new_items"], 2)
        self.assertTrue(knowledge.KNOWLEDGE_LOG.is_file())

    def test_ayni_icerik_ikinci_kez_yeni_sayilmaz(self):
        controller = FakeController({"konu": {"sources": [source("h1")]}})
        knowledge.run(controller, topics=("konu",))
        out = knowledge.run(controller, topics=("konu",))
        self.assertEqual(out["new_items"], 0)
        self.assertEqual(out["known_items"], 1)

    def test_degisen_icerik_yeni_sayilir(self):
        controller = FakeController({"konu": {"sources": [source("h1")]}})
        knowledge.run(controller, topics=("konu",))
        controller.by_topic["konu"] = {"sources": [source("h1"), source("h2")]}
        out = knowledge.run(controller, topics=("konu",))
        self.assertEqual(out["new_items"], 1)
        self.assertEqual(out["known_items"], 1)

    def test_model_cagrisi_ve_dis_aksiyon_sifir(self):
        controller = FakeController({"konu": {"sources": [source("h1")], "model_calls": 0}})
        out = knowledge.run(controller, topics=("konu",))
        self.assertEqual(out["model_calls"], 0)
        self.assertEqual(out["external_actions"], 0)

    def test_hicbir_sey_onerilmedigi_soylenir(self):
        out = knowledge.run(FakeController({}), topics=("konu",))
        self.assertIn("Action Firewall", out["note"])


class DayaniklilikTests(EnterContextMixin, unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.enterContext(patch.object(knowledge, "STATE_DIR", tmp))
        self.enterContext(patch.object(knowledge, "KNOWLEDGE_LOG", tmp / "knowledge.jsonl"))
        self.enterContext(patch.object(knowledge, "TOPICS_FILE", tmp / "topics.json"))

    def test_bir_konu_coktugunde_digerleri_devam_eder(self):
        controller = FakeController({"kotu": RuntimeError("ağ yok"),
                                     "iyi": {"sources": [source("h1")]}})
        out = knowledge.run(controller, topics=("kotu", "iyi"))
        self.assertEqual(out["failed_topics"], ["kotu"])
        self.assertEqual(out["new_items"], 1)

    def test_bozuk_satir_okumayi_durdurmaz(self):
        knowledge.KNOWLEDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        knowledge.KNOWLEDGE_LOG.write_text(
            '{"topic":"k","content_hash":"h1"}\nBOZUK SATIR\n', encoding="utf-8")
        controller = FakeController({"k": {"sources": [source("h1"), source("h2")]}})
        out = knowledge.run(controller, topics=("k",))
        self.assertEqual(out["new_items"], 1)

    def test_hashsiz_kaynak_atlanir(self):
        controller = FakeController({"k": {"sources": [{"url": "https://x.com"}]}})
        self.assertEqual(knowledge.run(controller, topics=("k",))["new_items"], 0)

    def test_enjeksiyon_isaretli_kaynak_raporlanir(self):
        controller = FakeController({"k": {"sources": [source("h9", injection=True)]}})
        out = knowledge.run(controller, topics=("k",))
        self.assertEqual(len(out["injection_flagged"]), 1)

    def test_snippet_uzunlugu_sinirli(self):
        uzun = "x" * 9000
        controller = FakeController({"k": {"sources": [source("h1", snippets=(uzun,))]}})
        knowledge.run(controller, topics=("k",))
        row = json.loads(knowledge.KNOWLEDGE_LOG.read_text(encoding="utf-8").splitlines()[0])
        self.assertLessEqual(len(row["snippet"]), knowledge.MAX_CONTENT_CHARS)


class KonuVeOzetTests(EnterContextMixin, unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.enterContext(patch.object(knowledge, "STATE_DIR", tmp))
        self.enterContext(patch.object(knowledge, "KNOWLEDGE_LOG", tmp / "knowledge.jsonl"))
        self.enterContext(patch.object(knowledge, "TOPICS_FILE", tmp / "topics.json"))

    def test_konu_dosyasi_yoksa_varsayilan(self):
        self.assertEqual(knowledge.load_topics(), knowledge.DEFAULT_TOPICS)

    def test_konu_dosyasi_okunur(self):
        knowledge.TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        knowledge.TOPICS_FILE.write_text(json.dumps({"topics": ["a", "b"]}), encoding="utf-8")
        self.assertEqual(knowledge.load_topics(), ("a", "b"))

    def test_bozuk_konu_dosyasi_varsayilana_duser(self):
        knowledge.TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        knowledge.TOPICS_FILE.write_text("{bozuk", encoding="utf-8")
        self.assertEqual(knowledge.load_topics(), knowledge.DEFAULT_TOPICS)

    def test_ozet_bos_depoda_cokmez(self):
        self.assertEqual(knowledge.summary()["total"], 0)

    def test_ozet_konu_ve_yayinci_sayar(self):
        controller = FakeController({"k": {"sources": [source("h1"), source("h2", publisher="b.com")]}})
        knowledge.run(controller, topics=("k",))
        out = knowledge.summary()
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["topics"][0]["count"], 2)
        self.assertEqual(len(out["publishers"]), 2)


if __name__ == "__main__":
    unittest.main()
