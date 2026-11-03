"""Karar kurulu testleri: sahte model, sıfır dış çağrı."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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
                             {"id": "O2", "karar": "SORGULA", "itiraz": "rakip fiyatı tek kaynak"},
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

    def test_radar_ozeti_girer(self):
        p = Path(self.tmp.name) / "panel.json"
        p.write_text(json.dumps({"sabah_ozeti": {"tarih": "2026-11-03", "uyarilar": ["X %25 indirim"]}}), encoding="utf-8")
        k = Kurul(self.iu, radar_panel=p)
        kalemler = k.sonuclar(self.agac(), SAAT)
        self.assertIn("radar", [x["tur"] for x in kalemler])
        self.assertEqual(k._denetci("_RADAR", {d.kod: d for d in deps()}), "MARKET_INT")


if __name__ == "__main__":
    unittest.main()
