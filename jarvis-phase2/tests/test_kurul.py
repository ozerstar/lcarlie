"""Karar kurulu testleri: sahte model, sıfır dış çağrı."""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_is_uretici import SahteDefter, SahteModel

from jarvis.is_uretici import Departman, IsUretici, Ortam, Uye
from jarvis.kurul import Kurul

SAAT = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)   # TR 12:00


def deps():
    def d(kod):
        return Departman(kod, kod.title(), "", uyeler=[Uye(kod.lower() + "_lider", kod, "iş")])
    return [d(k) for k in ("SEO", "WEB", "EXEC", "COMPETITOR_INT", "MARKET_INT", "CREATIVE_STRAT", "RED_TEAM")]


def cevap(mesajlar, kw):
    u = mesajlar[-1]["content"]
    if "Denetçi birim: WEB" in u:
        return {"denetimler": [{"kimlik": "S1", "guven": "YUKSEK", "anlam": "24 üründe meta yok, trafik kaybı.",
                                "oneriler": [
                                    {"baslik": "Meta açıklama taslaklarını yaz", "tip": "TASLAK", "departman": "SEO", "neden": "S1"},
                                    {"baslik": "Uydurma birime iş", "tip": "ANALIZ", "departman": "YOK", "neden": "-"}]},
                               {"kimlik": "S9", "anlam": "uydurma kimlik"}]}
    if "Denetçi birim: COMPETITOR_INT" in u:
        return {"denetimler": [{"kimlik": "S1", "guven": "ORTA", "anlam": "Rakip Kasım indirimi başlattı.",
                                "oneriler": [{"baslik": "Kasım kampanya fiyatını değiştir", "tip": "ONAY_GEREKTIREN",
                                              "departman": "CREATIVE_STRAT", "neden": "rakip"}]}]}
    if "RED TEAM" in u:
        return {"kararlar": [{"id": "O1", "karar": "KABUL", "itiraz": "dayanak sağlam"},
                             {"id": "O2", "karar": "KABUL", "itiraz": "rakip fiyatı tek kaynak"},
                             {"id": "O3", "karar": "RED", "itiraz": "eski iş, tekrar"},
                             {"id": "O99", "karar": "KABUL"}]}
    if "ana karar vericisisin" in u:
        return {"kararlar": [{"id": "O1", "karar": "YAP", "oncelik": 1, "gerekce": "hızlı kazanç"},
                             {"id": "O2", "karar": "YAP", "oncelik": 2, "gerekce": "sahip karar versin"},
                             {"id": "O3", "karar": "YAP", "oncelik": 1, "gerekce": "red teami yok say"}],
                "gunun_ozeti": "SEO eksikleri kapatılıyor; Kasım fiyatı senin kararın."}
    raise AssertionError("beklenmeyen istem: " + u[:80])


class TestKurul(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        kok = Path(self.tmp.name)
        self.model = SahteModel(cevap)
        self.onaylar = []
        self.o = Ortam(departmanlar=deps, uye_gorusleri=lambda d: [], arastirma_notlari=lambda k, g: [],
                       uret=self.model, defter=SahteDefter(), durum_dizini=kok, saat=lambda: SAAT,
                       oneri_ac=lambda a, m, s: self.onaylar.append((a, m, s)) or 501)
        self.iu = IsUretici(self.o, gunluk_tavan=50)
        teslim = kok / "t.md"
        teslim.write_text("# Teslim\n- 80 üründen 24'ünde meta açıklama yok", encoding="utf-8")
        agac = {"hedefler": [], "departmanlar": {
            "SEO": {"ad": "SEO", "gorevler": [
                {"id": "g1", "baslik": "Meta eksiklerini say", "tip": "ANALIZ", "durum": "TESLIM_EDILDI",
                 "teslim": {"kalite": "GECTI", "tarih": "2026-11-03T07:00:00+00:00", "yol": str(teslim), "ozet": "24 eksik"}},
                {"id": "g0", "baslik": "Eski teslim", "tip": "ANALIZ", "durum": "TESLIM_EDILDI",
                 "teslim": {"kalite": "GECTI", "tarih": "2026-10-20T07:00:00+00:00", "yol": "", "ozet": "eski"}},
                {"id": "o1", "baslik": "Instagram'da kampanya yayınla", "tip": "ONAY_GEREKTIREN",
                 "durum": "ONAY_BEKLIYOR", "cikti": "gönderi"}]}}}
        self.iu.agac_deposu.yaz(agac, SAAT)
        rk = kok / "programlar" / "rakip"
        rk.mkdir(parents=True)
        (rk / "2026-11-03-TR-1.md").write_text("Rakip X Kasım'da %30 indirim", encoding="utf-8")
        (rk / "2026-11-02-TR-1.md").write_text("dünkü", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def agac(self):
        return self.iu.agac_deposu.oku()

    def test_uctan_uca(self):
        s = Kurul(self.iu).calistir()
        self.assertEqual(s["sonuc"], 2)          # eski teslim ve dünkü rakip raporu girmez
        self.assertEqual(s["oneri"], 3)          # uydurma birim/kimlik atıldı + 1 birikmiş onay işi
        self.assertEqual(s["red"], 1)
        self.assertEqual(s["gorev"], 1)
        self.assertEqual(s["onaya"], 1)
        a = self.agac()
        seo = {g["id"]: g for g in a["departmanlar"]["SEO"]["gorevler"]}
        self.assertEqual(seo["o1"]["durum"], "KURUL_KAPATTI")      # red team RED -> EXEC YAP dese de gitmez
        self.assertIn("kurul", seo["g1"])
        yeni = [g for g in a["departmanlar"]["SEO"]["gorevler"] if g.get("kaynak") == "kurul"]
        self.assertEqual(len(yeni), 1)
        self.assertEqual(yeni[0]["baslik"], "Meta açıklama taslaklarını yaz")
        self.assertEqual(len(self.onaylar), 1)
        self.assertIn("Kasım kampanya fiyatını", self.onaylar[0][1])
        self.assertIn("hiçbir platforma otomatik yazılmaz", self.onaylar[0][1])
        rapor = Path(s["rapor"]).read_text(encoding="utf-8")
        self.assertIn("Kasım fiyatı senin kararın", rapor)
        self.assertIn("RED: eski iş", rapor)
        # denetçi yönlendirmesi: SEO teslimi WEB'e, rakip raporu COMPETITOR_INT'e
        istemler = [m[0][-1]["content"] for m in self.model.cagri]
        self.assertTrue(any("Denetçi birim: WEB" in i for i in istemler))
        self.assertTrue(any("Denetçi birim: COMPETITOR_INT" in i for i in istemler))

    def test_ikinci_kosu_ayni_sonucu_denetlemez(self):
        Kurul(self.iu).calistir()
        n = len(self.model.cagri)
        s = Kurul(IsUretici(self.o, gunluk_tavan=50)).calistir()
        self.assertEqual(s["sonuc"], 0)
        self.assertEqual(len(self.model.cagri), n)   # denetlenecek bir şey yok -> model çağrısı yok

    def test_kuru_calisma_yazmaz(self):
        s = Kurul(IsUretici(self.o, gunluk_tavan=50, kuru=True)).calistir()
        self.assertEqual(s["onaya"], 0)
        self.assertEqual(self.onaylar, [])
        self.assertNotIn("kurul", {g["id"]: g for g in self.agac()["departmanlar"]["SEO"]["gorevler"]}["g1"])

    def test_red_team_cevapsizsa_karar_yok(self):
        def sessiz(m, kw):
            if "RED TEAM" in m[-1]["content"]:
                return "bozuk"
            return cevap(m, kw)
        self.model.cevaplar = sessiz
        s = Kurul(self.iu).calistir()
        self.assertEqual(s["gorev"], 0)
        self.assertEqual(s["onaya"], 0)
        o1 = {g["id"]: g for g in self.agac()["departmanlar"]["SEO"]["gorevler"]}["o1"]
        self.assertEqual(o1["durum"], "ONAY_BEKLIYOR")   # karar yoksa birikmiş iş kapanmaz

    def test_partial_review_does_not_enable_unreviewed_dispatch(self):
        k = Kurul(self.iu)
        k.sorgula = lambda os: {"O3": {"karar": "RED", "itiraz": "eski"}}
        r = k.calistir()
        self.assertEqual((r["gorev"], r["onaya"]), (0, 0))
        self.assertEqual(len(self.agac()["kurul"]["bekleyen_denetimler"]), 2)
        self.assertFalse(any("ana karar vericisisin" in m[0][-1]["content"] for m in self.model.cagri))

    def test_explicit_unresolved_review_cannot_dispatch(self):
        k = Kurul(self.iu)
        k.sorgula = lambda os: {o["id"]: {"karar": "SORGULA", "itiraz": "kaynak eksik"} for o in os}
        r = k.calistir()
        self.assertEqual((r["gorev"], r["onaya"]), (0, 0))
        self.assertEqual(len(self.agac()["kurul"]["bekleyen_denetimler"]), 2)

    def test_outage_replays_saved_review_after_source_window(self):
        k = Kurul(self.iu)
        k.sorgula = lambda os: (_ for _ in ()).throw(RuntimeError("offline"))
        k.calistir()
        self.o.saat = lambda: SAAT + timedelta(days=3)
        n = len(self.model.cagri)
        r = Kurul(IsUretici(self.o, gunluk_tavan=50)).calistir()
        self.assertEqual((r["gorev"], r["onaya"]), (1, 1))
        self.assertFalse(any("Denetçi birim:" in m[0][-1]["content"] for m in self.model.cagri[n:]))
        self.assertEqual(self.agac()["kurul"]["bekleyen_denetimler"], [])

    def test_deferred_and_capped_items_remain_pending(self):
        k = Kurul(self.iu)
        k.karar_ver = lambda os, h: ({o["id"]: {"karar": "BEKLET", "gerekce": "sonra"} for o in os}, "")
        k.calistir()
        self.assertEqual(len(self.agac()["kurul"]["bekleyen_denetimler"]), 2)
        with patch("jarvis.kurul.GOREV_TAVAN", 0), patch("jarvis.kurul.ONAY_TAVAN", 0):
            Kurul(self.iu).calistir()
        self.assertEqual(len(self.agac()["kurul"]["bekleyen_denetimler"]), 2)
        r = Kurul(self.iu).calistir()
        self.assertEqual((r["gorev"], r["onaya"]), (1, 1))

    def test_handoff_replay_preserves_exact_payload_across_days(self):
        for result in (None, False, True, 0, -1):
            self.o.oneri_ac = lambda a, m, s: self.onaylar.append((a, m, s)) or result
            r = Kurul(IsUretici(self.o, gunluk_tavan=50)).calistir()
            self.assertEqual(r["onaya"], 0)
        self.assertEqual(len(set(self.onaylar)), 1)
        self.o.saat = lambda: SAAT + timedelta(days=2)
        self.o.oneri_ac = lambda a, m, s: self.onaylar.append((a, m, s)) or 502
        # Frozen outbox replay must not need a new model result.
        self.model.cevaplar = lambda *args: (_ for _ in ()).throw(AssertionError("model called"))
        r = Kurul(IsUretici(self.o, gunluk_tavan=50)).calistir()
        self.assertEqual(r["onaya"], 1)
        self.assertEqual(len(set(self.onaylar)), 1)
        self.assertEqual(self.agac()["kurul"]["bekleyen_denetimler"], [])

    def test_interrupted_callback_replays_without_new_proposal(self):
        def interrupted(a, m, s):
            self.onaylar.append((a, m, s))
            raise KeyboardInterrupt()
        self.o.oneri_ac = interrupted
        with self.assertRaises(KeyboardInterrupt):
            Kurul(self.iu).calistir()
        self.o.oneri_ac = lambda a, m, s: self.onaylar.append((a, m, s)) or 501
        r = Kurul(IsUretici(self.o, gunluk_tavan=50)).calistir()
        self.assertEqual(r["gorev"], 0)  # acknowledged internal task is not regenerated
        self.assertEqual(r["onaya"], 1)
        self.assertEqual(len(set(self.onaylar)), 1)

    def test_legacy_terminal_checkpoint_is_reconciled_after_interruption(self):
        a = self.agac()
        g = a["departmanlar"]["SEO"]["gorevler"][2]
        g["kurul_oneri"] = {"anahtar": "old-ack", "baslik": g["baslik"], "tip": "ONAY_GEREKTIREN",
            "departman": "SEO", "tamamlandi": "ONAYA_GITTI", "onay_id": 42,
            "rt": {"karar": "KABUL", "itiraz": ""}, "karar": {"karar": "YAP"}}
        self.iu.agac_deposu.yaz(a, SAAT)
        Kurul(self.iu).calistir()
        g = next(g for g in self.agac()["departmanlar"]["SEO"]["gorevler"] if g["id"] == "o1")
        self.assertEqual(g["durum"], "ONAYA_GITTI")
        self.assertFalse(any(a == "old-ack" for a, _, _ in self.onaylar))

    def test_unrelated_similar_task_is_not_acknowledgement(self):
        a = self.agac()
        a["departmanlar"]["SEO"]["gorevler"].append({"id": "unrelated", "durum": "ACIK",
            "baslik": "Meta açıklama taslaklarını yaz"})
        self.iu.agac_deposu.yaz(a, SAAT)
        r = Kurul(self.iu).calistir()
        self.assertEqual(r["gorev"], 0)
        pending = self.agac()["kurul"]["bekleyen_denetimler"]
        self.assertEqual(pending[0]["kalem"]["ref"], "g1")
        self.assertNotIn("tamamlandi", pending[0]["oneriler"][0])

    def test_pending_processing_is_bounded_without_dropping_tail(self):
        k = Kurul(self.iu)
        k.sorgula = lambda os: {}
        k.calistir()
        seen = []
        k.sorgula = lambda os: seen.extend(os) or {}
        with patch("jarvis.kurul.SONUC_TAVAN", 1):
            k.calistir()
        # One saved source proposal plus one independently bounded legacy item.
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(self.agac()["kurul"]["bekleyen_denetimler"]), 2)

    def test_radar_ozeti_girer(self):
        p = Path(self.tmp.name) / "panel.json"
        p.write_text(json.dumps({"sabah_ozeti": {"tarih": "2026-11-03", "uyarilar": ["X %25 indirim"]}}), encoding="utf-8")
        k = Kurul(self.iu, radar_panel=p)
        kalemler = k.sonuclar(self.agac(), SAAT)
        self.assertIn("radar", [x["tur"] for x in kalemler])
        self.assertEqual(k._denetci("_RADAR", {d.kod: d for d in deps()}), "MARKET_INT")

    def test_missing_or_shared_reviewer_never_falls_back_to_producer(self):
        k = Kurul(self.iu)
        seo = deps()[0]
        self.assertIsNone(k._denetci("SEO", {"SEO": seo}))
        shared = Departman("WEB", "Web", "", uyeler=seo.uyeler)
        self.assertIsNone(k._denetci("SEO", {"SEO": seo, "WEB": shared}))
        executive = next(d for d in deps() if d.kod == "EXEC")
        self.assertIsNone(k._denetci("EXEC", {"EXEC": executive}))
        self.assertEqual(k._denetci("SEO", {"SEO": seo, "EXEC": executive}), "EXEC")

    def test_blocked_source_survives_age_window_until_reviewer_returns(self):
        tree = self.agac()
        tree["departmanlar"]["SEO"]["gorevler"] = [tree["departmanlar"]["SEO"]["gorevler"][0]]
        self.iu.agac_deposu.yaz(tree, SAAT)
        (Path(self.tmp.name) / "programlar/rakip/2026-11-03-TR-1.md").unlink()
        self.o.departmanlar = lambda: [deps()[0]]
        result = Kurul(self.iu).calistir()
        self.assertEqual(result["denetci_bekliyor"], 1)
        self.assertEqual(len(self.agac()["kurul"]["bekleyen_kaynaklar"]), 1)
        self.assertNotIn("kurul", self.agac()["departmanlar"]["SEO"]["gorevler"][0])
        self.assertEqual(len(self.model.cagri), 0)
        self.o.departmanlar = deps
        self.o.saat = lambda: SAAT + timedelta(days=3)
        result = Kurul(IsUretici(self.o, gunluk_tavan=50)).calistir()
        self.assertEqual(result["gorev"], 1)
        self.assertEqual(result["denetci_bekliyor"], 0)
        self.assertEqual(self.agac()["kurul"]["bekleyen_kaynaklar"], [])

    def test_saved_self_review_cannot_replay_frozen_owner_payload(self):
        tree = self.agac()
        tree["departmanlar"]["SEO"]["gorevler"] = [tree["departmanlar"]["SEO"]["gorevler"][0]]
        proposal = {"anahtar": "self-reviewed", "tip": "ONAY_GEREKTIREN", "departman": "SEO", "baslik": "Unsafe old proposal",
                    "rt": {"karar": "KABUL", "itiraz": ""}, "karar": {"karar": "YAP", "gerekce": ""},
                    "onay_payload": {"anahtar": "self-reviewed", "metin": "old", "sebep": "old"}}
        tree["kurul"] = {"bekleyen_denetimler": [{"kalem": {"tur": "teslim", "ref": "g1", "dep": "SEO", "baslik": "Old"},
            "denetci": "SEO", "guven": "YUKSEK", "sorun": "", "anlam": "Self-reviewed", "oneriler": [proposal]}]}
        self.iu.agac_deposu.yaz(tree, SAAT)
        k = Kurul(self.iu)
        with patch.object(k, "sonuclar", return_value=[]):
            result = k.calistir()
        self.assertEqual((result["gorev"], result["onaya"]), (0, 0))
        self.assertEqual(result["denetci_bekliyor"], 1)
        self.assertEqual(self.onaylar, [])
        self.assertIn("engel", self.agac()["kurul"]["bekleyen_denetimler"][0])


if __name__ == "__main__":
    unittest.main()
