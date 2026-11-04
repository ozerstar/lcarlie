import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

from radar import ajan, claims, config, content, ingest, leads, outbox, regulation, reports
from radar.db import connect, jload
from radar.pricing import PriceBook
from radar.util import find_numbers, iso, now

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def obs(kind, value=None, product=None, url="https://www.trendyol.com/x/p-1", excerpt=None, ago_h=1, **kw):
    o = {"kind": kind, "value": value, "product": product, "source_url": url,
         "fetched_at": iso(now() - dt.timedelta(hours=ago_h))}
    if excerpt is not None:
        o["excerpt"] = excerpt
    o.update(kw)
    return o


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = config.load(os.path.join(self.tmp, "yok.json"), base_dir=self.tmp)
        self.cfg["price_list"] = os.path.join(ROOT, "data", "fiyat_listesi.json")
        self.cfg["owner"] = {"name": "Özer", "whatsapp": "+905550000000", "email": ""}
        self.conn = connect(os.path.join(self.tmp, "t.db"))
        self.book = PriceBook(self.cfg["price_list"])

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp)

    def run_ingest(self, brands, run_id=None):
        return ingest.ingest(self.conn, {"run_id": run_id, "source": "test", "brands": brands}, self.cfg, self.book)

    def brand(self, name):
        return self.conn.execute("SELECT * FROM brands WHERE name=?", (name,)).fetchone()


class TestUtil(unittest.TestCase):
    def test_numbers(self):
        self.assertIn(1450.9, find_numbers("Fiyat: 1.450,90 TL"))
        self.assertIn(1450.0, find_numbers("₺1.450"))
        self.assertIn(1299.0, find_numbers("1299 TL"))
        self.assertIn(14.5, find_numbers("14,50"))


class TestClaims(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(claims.check("Egzamayı tedavi eder, mucize krem")["durum"], "YASAK")
        self.assertEqual(claims.check("Dermatolog onaylı formül")["durum"], "DİKKAT")
        self.assertEqual(claims.check("Cildinize nem ve yumuşaklık hissi veren gece ritüeli")["durum"], "UYGUN")


class TestIngest(Base):
    def test_validation_rejects_hallucination(self):
        r = self.run_ingest([{"name": "Marka A", "texts": ["bitkisel krem"], "observations": [
            obs("price", 1500, "Krem", excerpt="Sepette 1.299 TL"),        # alıntıda yok → red
            obs("price", 1500, "Krem", url="", excerpt="1.500 TL"),         # link yok → red
            obs("price", 1500, "Krem", excerpt="1.500 TL", ago_h=-5),       # gelecek → red
            obs("price", 1500, "Krem", excerpt="1.500 TL", ago_h=24 * 30),  # eski → red
            obs("price", 1500, "Krem", excerpt="İndirimli fiyat 1.500 TL"),  # geçerli
        ]}])
        self.assertEqual(r["kabul"], 1)
        self.assertEqual(len(r["red"]), 4)
        reasons = " ".join(x["neden"] for x in r["red"])
        self.assertIn("uydurma", reasons)

    def test_color_cosmetics_filtered_and_never_back(self):
        self.run_ingest([{"name": "Renkli X", "observations": [
            obs("product", product="Mat Ruj 01"), obs("product", product="Maskara Volume")]}])
        self.assertEqual(self.brand("Renkli X")["status"], "filtered")
        r = self.run_ingest([{"name": "Renkli X", "observations": [obs("product", product="Nemlendirici")]}])
        self.assertTrue(r["atlanan"])

    def test_filters_and_score(self):
        self.run_ingest([{"name": "Doğa Lab", "origin": "TR", "first_seen_hint": iso(now() - dt.timedelta(days=60)),
                          "texts": ["Bitkisel onarıcı balsam, eczanelerde satışta"],
                          "observations": [obs("price", 2300, "Onarıcı Balsam", category="vucut", excerpt="2.300,00 TL")]}])
        b = self.brand("Doğa Lab")
        self.assertEqual(b["status"], "candidate")
        d = jload(b["detail"])
        for k in ("fiyat_bandi", "yeni_giris", "dogal", "tedavi_benzeri", "kanal"):
            self.assertTrue(d["kriterler"][k]["gecti"], k)
        self.assertEqual(b["score"], 25 + 15 + 15 + 15 + 15)

    def test_cheap_unmatched_is_unqualified(self):
        self.run_ingest([{"name": "Ucuz Y", "texts": ["günlük krem"],
                          "observations": [obs("price", 150, "Krem", category="yuz", excerpt="150 TL")]}])
        self.assertEqual(self.brand("Ucuz Y")["status"], "unqualified")

    def test_double_verification_price_drop(self):
        self.run_ingest([{"name": "Rakip Z", "texts": ["bitkisel"],
                          "observations": [obs("price", 2000, "Serum", category="yuz", excerpt="2.000 TL")]}], "r1")
        b = self.brand("Rakip Z")
        self.conn.execute("UPDATE brands SET status='active' WHERE id=?", (b["id"],)); self.conn.commit()
        r = self.run_ingest([{"name": "Rakip Z", "observations": [obs("price", 1400, "Serum", excerpt="1.400 TL")]}], "r2")
        self.assertEqual(r["bekleyen"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0], 0)
        self.assertEqual(len(ingest.recheck_list(self.conn)), 1)
        # aynı taramada tekrar görmek teyit sayılmaz
        r = self.run_ingest([{"name": "Rakip Z", "observations": [obs("price", 1400, "Serum", excerpt="1.400 TL")]}], "r2")
        self.assertEqual(r["onaylanan"], 0)
        r = self.run_ingest([{"name": "Rakip Z", "observations": [obs("price", 1400, "Serum", excerpt="1.400 TL")]}], "r3")
        self.assertEqual(r["onaylanan"], 1)
        a = self.conn.execute("SELECT * FROM alerts").fetchone()
        self.assertIn("indirim %30", a["text"])
        self.assertEqual(len(outbox.pending(self.conn)), 0)  # Özer'e giden uyarı onay beklemez
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM outbox WHERE status='approved'").fetchone()[0], 1)

    def test_glitch_discarded(self):
        self.run_ingest([{"name": "Rakip G", "texts": ["bitkisel"],
                          "observations": [obs("price", 2000, "Krem", excerpt="2.000 TL")]}], "r1")
        self.conn.execute("UPDATE brands SET status='active'"); self.conn.commit()
        self.run_ingest([{"name": "Rakip G", "observations": [obs("price", 200, "Krem", excerpt="200 TL")]}], "r2")
        self.run_ingest([{"name": "Rakip G", "observations": [obs("price", 2000, "Krem", excerpt="2.000 TL")]}], "r3")
        st = self.conn.execute("SELECT status FROM pending_changes").fetchone()[0]
        self.assertEqual(st, "discarded")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0], 0)

    def test_new_product_confirmed(self):
        self.run_ingest([{"name": "Rakip N", "texts": ["doğal"], "observations": [obs("product", product="A Krem")]}], "r1")
        self.conn.execute("UPDATE brands SET status='active'"); self.conn.commit()
        r = self.run_ingest([{"name": "Rakip N", "observations": [
            obs("product", product="B Serum"), obs("price", 1800, "B Serum", excerpt="1.800 TL")]}], "r2")
        self.assertEqual(r["bekleyen"], 1)
        r = self.run_ingest([{"name": "Rakip N", "observations": [obs("price", 1800, "B Serum", excerpt="1.800 TL")]}], "r3")
        self.assertEqual(r["onaylanan"], 1)
        self.assertIn("yeni ürün", self.conn.execute("SELECT text FROM alerts").fetchone()[0])


class TestMonthlyAndBrief(Base):
    def test_monthly_diff_and_passive(self):
        self.run_ingest([{"name": "Aylık M", "texts": ["bitkisel"], "observations": [
            obs("price", 1000, "Krem", excerpt="1.000 TL"), obs("channel", "eczane")]}], "r1")
        self.conn.execute("UPDATE brands SET status='active'"); self.conn.commit()
        reports.monthly(self.conn, self.cfg, "2026-08")
        self.run_ingest([{"name": "Aylık M", "observations": [
            obs("price", 1050, "Krem", excerpt="1.050 TL"), obs("product", product="Yeni Tonik")]}], "r2")
        self.run_ingest([{"name": "Aylık M", "observations": [obs("product", product="Yeni Tonik")]}], "r3")
        _, text = reports.monthly(self.conn, self.cfg, "2026-09")
        self.assertIn("1,000 → 1,050", text)
        self.assertIn("Yeni ürün: Yeni Tonik", text)
        for m in ("2026-10", "2026-11", "2026-12"):
            reports.monthly(self.conn, self.cfg, m)
        self.assertEqual(self.brand("Aylık M")["status"], "passive")

    def test_brief_and_approval_gate(self):
        self.run_ingest([{"name": "Brief B", "texts": ["bitkisel balsam eczane"],
                          "observations": [obs("price", 2500, "Balsam", category="vucut", excerpt="2.500 TL")]}])
        mid = outbox.enqueue(self.conn, "whatsapp", "+903120000000", "Merhaba", to_owner=False)
        text = reports.morning_brief(self.conn, self.cfg)
        self.assertIn("Brief B", text)
        self.assertIn("https://www.trendyol.com", text)
        self.assertIn("ONAY BEKLEYEN 1", text)
        self.assertNotIn("Brief B", reports.morning_brief(self.conn, self.cfg))  # ikinci kez raporlanmaz
        sent, _ = outbox.send_approved(self.conn, self.cfg)
        st = self.conn.execute("SELECT status FROM outbox WHERE id=?", (mid,)).fetchone()[0]
        self.assertEqual(st, "pending_approval")  # onaysız mesaj gönderilmedi
        outbox.decide(self.conn, mid, True)
        # Gönderici (WAHA/webhook) yoksa mesaj 'gönderildi' sayılmaz (eski sürüm klasöre yazıp 'sent' diyordu).
        _, hatalar = outbox.send_approved(self.conn, self.cfg)
        self.assertEqual(self.conn.execute("SELECT status FROM outbox WHERE id=?", (mid,)).fetchone()[0], "approved")
        self.assertTrue(any("WhatsApp gönderici yok" in h for h in hatalar))
        giden = []
        os.environ.update({"WAHA_URL": "http://127.0.0.1:3000", "WAHA_API_KEY": "k"})
        try:
            outbox.send_approved(self.conn, self.cfg, post=lambda u, p, h=None: giden.append((u, p, h)) or {})
        finally:
            del os.environ["WAHA_URL"], os.environ["WAHA_API_KEY"]
        self.assertEqual(self.conn.execute("SELECT status FROM outbox WHERE id=?", (mid,)).fetchone()[0], "sent")
        waha = [g for g in giden if g[0].endswith("/api/sendText")]
        self.assertEqual(waha[0][1]["chatId"], "903120000000@c.us")
        self.assertEqual(waha[0][2], {"X-Api-Key": "k"})
        self.assertTrue(os.listdir(self.cfg["delivery"]["spool_dir"]))

    def test_whatsapp_jarvis_koprusu(self):
        self.cfg["owner"] = {"whatsapp": "905421886937"}
        outbox.to_owner(self.conn, self.cfg, "☀️ özet\nsatır 2", "Sabah özeti", ref="ozet:2026-10-30")
        mid = outbox.enqueue(self.conn, "whatsapp", "03121112233", "Merhaba eczane", to_owner=False)
        outbox.decide(self.conn, mid, True)
        cagrilar = []

        def calistir(komut, girdi):
            cagrilar.append(json.loads(girdi))
            return '{"gonderildi": true, "yol": "sablon", "wamid": "x"}'
        os.environ["JARVIS_WHATSAPP_CMD"] = "python kopru.py"
        try:
            orijinal = outbox._jarvis_whatsapp
            outbox._jarvis_whatsapp = lambda c, cfg, m, calistir=calistir: orijinal(c, cfg, m, calistir)
            sent, hatalar = outbox.send_approved(self.conn, self.cfg)
        finally:
            outbox._jarvis_whatsapp = orijinal
            del os.environ["JARVIS_WHATSAPP_CMD"]
        self.assertEqual(len(cagrilar), 1)                       # yalnız sahibe giden özet köprüye gitti
        self.assertEqual(cagrilar[0]["telefon"], "905421886937")
        self.assertEqual(len(cagrilar[0]["kisa"]), 5)
        self.assertTrue(all("\n" not in k for k in cagrilar[0]["kisa"]))
        st = self.conn.execute("SELECT status FROM outbox WHERE id=?", (mid,)).fetchone()[0]
        self.assertEqual(st, "approved")                          # eczane mesajı bu yoldan GİTMEDİ

    def test_satis_jarvis_tablosundan(self):
        from radar import satis
        cikti = '{"kanal":"wix","dun":1,"dun_tutar":2100,"yedi":3,"yedi_tutar":5300}\n' \
                '{"kanal":"trendyol","dun":0,"dun_tutar":0,"yedi":0,"yedi_tutar":0}\n'
        s = satis.db_ozet(psql=lambda sql: cikti)
        self.assertEqual(s, {"wix dün": "1 sipariş, 2,100 TL", "wix 7 gün": "3 sipariş, 5,300 TL"})
        self.assertEqual(satis.db_ozet(psql=lambda sql: ""), {"Tüm kanallar": "son 7 günde sipariş yok"})

    def test_telegram_uzun_mesaji_parcalar(self):
        self.cfg["owner"] = {"telegram_chat_id": "12345"}
        outbox.to_owner(self.conn, self.cfg, "\n".join(f"satır {i} " + "x" * 90 for i in range(100)), "Özet")
        giden = []
        os.environ["TELEGRAM_BOT_TOKEN"] = "TEST"
        try:
            sent, hatalar = outbox.send_approved(self.conn, self.cfg,
                                                 post=lambda u, p, h=None: giden.append((u, p)) or {"ok": True})
        finally:
            del os.environ["TELEGRAM_BOT_TOKEN"]
        self.assertEqual((sent, hatalar), (1, []))
        self.assertGreater(len(giden), 1)
        self.assertTrue(all(len(p["text"]) <= 4096 and p["chat_id"] == "12345" for _, p in giden))
        self.assertTrue(giden[0][0].endswith("/botTEST/sendMessage"))

    def test_health_and_backup(self):
        ingest.ingest(self.conn, {"source": "trendyol", "source_status": [{"source": "trendyol", "ok": False, "error": "403"}],
                                  "brands": []}, self.cfg, self.book)
        reports.backup(self.conn, self.cfg)
        h = reports.health(self.conn, self.cfg)
        self.assertIn("❌ trendyol", h)
        self.assertIn("radar-", h)


class TestLeadsRegContent(Base):
    def test_leads_dedupe_and_approval(self):
        os.environ["GOOGLE_PLACES_API_KEY"] = "x"
        fake = lambda url, payload, headers: {"places": [
            {"id": "P1", "displayName": {"text": "Güneş Eczanesi"}, "formattedAddress": "Çankaya",
             "nationalPhoneNumber": "0312 000 00 00", "googleMapsUri": "https://maps.google.com/?cid=1",
             "businessStatus": "OPERATIONAL"}]}
        self.cfg["leads"]["kaynak"] = "places"
        r = leads.find(self.conn, self.cfg, self.book, post=fake)
        self.assertEqual(r["yeni"], 1)
        self.assertEqual(leads.find(self.conn, self.cfg, self.book, post=fake)["yeni"], 0)
        p = outbox.pending(self.conn)
        self.assertEqual(len(p), 1)
        self.assertNotEqual(claims.check(p[0]["body"])["durum"], "YASAK")

    def test_osm_leads(self):
        cevap = {"elements": [
            {"type": "node", "id": 7, "tags": {"amenity": "pharmacy", "name": "Defne Eczanesi", "phone": "+90 312 111 22 33",
                                              "addr:street": "Atatürk Blv.", "addr:district": "Çankaya"}},
            {"type": "node", "id": 8, "tags": {"amenity": "pharmacy"}},                      # adsız: atlanır
            {"type": "way", "id": 9, "tags": {"amenity": "pharmacy", "name": "Telefonsuz Eczane"}}]}
        self.cfg["leads"].update({"osm_iller": ["Ankara"], "osm_turler": ["eczane"]})
        r = leads.osm_bul(
            self.conn, self.cfg, self.book, getir=lambda u, q: cevap)
        self.assertEqual(r["yeni"], 2)
        self.assertEqual(leads.osm_bul(self.conn, self.cfg, self.book, getir=lambda u, q: cevap)["yeni"], 0)
        p = outbox.pending(self.conn)
        self.assertEqual([m["recipient"] for m in p], ["+90 312 111 22 33"])   # yalnız telefonlu, onay bekliyor
        src = self.conn.execute("SELECT source_url FROM leads WHERE name='Defne Eczanesi'").fetchone()[0]
        self.assertEqual(src, "https://www.openstreetmap.org/node/7")

    def test_regulation_diff(self):
        pages = iter(["<p>Eski duyuru metni burada yer alıyor</p>",
                      "<p>Eski duyuru metni burada yer alıyor</p><p>Kozmetik ürün reklamlarına ilişkin yeni kılavuz</p>"])
        self.cfg["regulation"]["urls"] = ["https://www.titck.gov.tr/duyuru"]
        regulation.check(self.conn, self.cfg, get=lambda u: next(pages))
        r = regulation.check(self.conn, self.cfg, get=lambda u: next(pages))
        self.assertEqual(len(r["degisen"]), 1)
        self.assertIn("Kozmetik ürün reklamlarına", reports.morning_brief(self.conn, self.cfg))

    def test_content_blocks_claims(self):
        fake = lambda url, payload, headers: {"choices": [{"message": {"content": "Bu krem egzamayı tedavi eder."}}]}
        for k, v in (("LLM_BASE_URL", "https://x.ai/v1"), ("LLM_API_KEY", "k"), ("LLM_MODEL", "m")):
            os.environ[k] = v
        r = content.weekly(self.conn, self.cfg, self.book, post=fake)
        self.assertEqual(r["engellenen"], 7)
        for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
            del os.environ[k]


class TestDuzeltmeler(Base):
    """29.10.2026 incelemesinde bulunan hatalar."""

    def test_buyuk_harf_yabanci_kelime_eslesir(self):
        self.run_ingest([{"name": "Glow Lab", "texts": ["MATTE LIPSTICK COLLECTION"],
                          "observations": [obs("product", product="LIPSTICK RED")]}])
        self.assertEqual(self.brand("Glow Lab")["status"], "filtered")
        self.run_ingest([{"name": "Verde", "texts": ["ORGANIC FACE CREAM"],
                          "observations": [obs("product", product="Face Cream")]}])
        self.assertIn("dogal", jload(self.brand("Verde")["detail"])["eslesen"])

    def test_iddia_filtresi_yeni_kaliplar(self):
        for t in ("Pişik önleyici krem", "Bitkisel lifting kremi", "KLINIK OLARAK KANITLANMIŞ"):
            self.assertEqual(claims.check(t)["durum"], "DİKKAT", t)
        self.assertEqual(claims.check("ŞİFALI MERHEM")["durum"], "YASAK")

    def test_trendyol_fiyati_trendyol_fiyatimizla_karsilastirilir(self):
        ps = self.book.band(1300, "yuz", 0.9)
        ty = self.book.band(1300, "yuz", 0.9, trendyol=True)
        self.assertGreater(ps["oran"], ty["oran"])
        self.assertEqual(ty["ref"], 1380)

    def test_lead_taslaginda_kanitsiz_beyan_yok(self):
        body, _ = leads.draft_message("Örnek Eczanesi", "eczane", self.book)
        for beyan in ("GMP", "ISO 22716", "Ankara merkezli"):
            self.assertNotIn(beyan, body)
        body, _ = leads.draft_message("X", "eczane", self.book, "Onaylı tanıtım cümlesi.")
        self.assertIn("Onaylı tanıtım cümlesi.", body)

    def test_panel_dosyasi_kisi_verisi_icermez(self):
        self.conn.execute("INSERT INTO leads(place_id,name,type,address,phone,found_at) VALUES('p1','Örnek Eczanesi',"
                          "'eczane','Gizli Sok. 5','0312 555 00 00',?)", (iso(now()),))
        outbox.enqueue(self.conn, "whatsapp", "0312 555 00 00", "taslak", "Tanışma")
        reports.morning_brief(self.conn, self.cfg)
        outbox.to_owner(self.conn, self.cfg, "☀️ özet metni", "Sabah özeti", ref="ozet:2026-10-29")
        yol = reports.panel(self.conn, self.cfg)
        metin = open(yol, encoding="utf-8").read()
        self.assertNotIn("555 00 00", metin)
        self.assertNotIn("Gizli Sok", metin)
        d = json.loads(metin)
        self.assertEqual(d["sabah_ozeti"]["body"], "☀️ özet metni")
        self.assertEqual(d["onay_bekleyen_mesaj"], 1)

    def test_eczane_kanali_tek_basina_aday_yapmaz(self):
        self.run_ingest([{"name": "Signal", "texts": ["Signal Nane Ferahlığı Diş Macunu 100 ml"],
                          "observations": [obs("channel", value="eczane")]}])
        self.assertEqual(self.brand("Signal")["status"], "unqualified")

    def test_parfum_ve_prezervatif_kapsam_disi(self):
        self.run_ingest([{"name": "Dunhill", "observations": [
            obs("price", 4200, "Dunhill Icon Edp 100 ml", excerpt="Dunhill Icon Edp 100 ml 4.200 TL"),
            obs("product", product="Dunhill Desire Blue Eau De Toilette 100 ml")]}])
        self.assertEqual(self.brand("Dunhill")["status"], "filtered")

    def test_trendyol_chrome_satirlari(self):
        from radar import trendyol
        p = trendyol.satirlardan_payload([
            "tera-dermokozmetik|1.150 TL|1171563805|TERA DERMOKOZMETİK ÇATLAK ÖNLEYİCİ KREM",
            "bioderma|1.827,50 TL|31632972|En Çok Favorilenen 2. Ürün",
            "motiflor|1.299 TL|32848498|Motiflor Probiyotik Gyno Vajinal Supozituar 10 Adet"])
        self.assertEqual(len(p["atlanan"]), 1)              # rozet adlı kartta fiyat yazılmaz
        fiyat = [o for b in p["brands"] for o in b["observations"] if o["kind"] == "price"]
        self.assertEqual(fiyat[0]["value"], 1150.0)
        self.assertEqual(fiyat[0]["source_url"], "https://www.trendyol.com/tera-dermokozmetik/x-p-1171563805")
        rep = self.run_ingest(p["brands"])
        self.assertEqual(rep["red"], [])
        self.assertEqual(self.brand("Motiflor")["status"], "filtered")
        self.assertEqual(self.brand("Tera Dermokozmetik")["status"], "candidate")

    def test_fiyat_listesi_magazayla_uyumlu(self):
        adlar = {i["ad"]: i for i in self.book.items}
        self.assertIn("DORSIVIA", adlar)
        self.assertEqual(adlar["LIFTELLE"]["kategori"], "vucut")
        self.assertNotIn("Önleyici", adlar["MINISOOTH"]["aciklama"])


SAYFA = ("<html><body><h1>Verde Botanik Onarıcı Balsam 50 ml</h1><p>Bitkisel içerikli onarıcı balsam, eczanelerde.</p>"
         "<span>Onarıcı Balsam 50 ml 1.450 TL</span><p>1.234 Değerlendirme</p>"
         + "<p>ürün açıklaması</p>" * 30 + "</body></html>")


class TestAjan(Base):
    def _uret(self, cikti):
        return lambda mesajlar, **kw: {"text": json.dumps(cikti, ensure_ascii=False)}

    def test_dogru_alinti_kabul_uydurma_red(self):
        cikti = {"markalar": [{"marka": "Verde Botanik",
                               "tanitim": ["Bitkisel içerikli onarıcı balsam, eczanelerde.", "Dermatolog onaylı mucize"],
                               "urunler": [{"ad": "Onarıcı Balsam 50 ml", "kategori": "vucut", "fiyat": 1450,
                                            "alinti": "Onarıcı Balsam 50 ml 1.450 TL"},
                                           {"ad": "Gece Serumu", "fiyat": 990, "alinti": "Gece Serumu 990 TL"}],
                               "kanallar": [{"kanal": "eczane", "alinti": "eczanelerde"}],
                               "yorum_sayisi": {"deger": 1234, "alinti": "1.234 Değerlendirme"}},
                              {"marka": "Hayalet Marka", "urunler": []}]}
        getir = lambda u: ("https://www.trendyol.com/verde/balsam-p-1", SAYFA)
        markalar, durum, red = ajan.sayfa_cikar("https://x.y/z", getir, self._uret(cikti))
        self.assertTrue(durum["ok"])
        self.assertEqual([m["name"] for m in markalar], ["Verde Botanik"])
        kinds = sorted(o["kind"] for o in markalar[0]["observations"])
        self.assertEqual(kinds, ["channel", "price", "product", "review_count"])
        self.assertEqual(markalar[0]["texts"], ["Bitkisel içerikli onarıcı balsam, eczanelerde."])
        self.assertEqual(red, 2)  # uydurma 'Gece Serumu' + sayfada olmayan 'Hayalet Marka'
        rep = self.run_ingest(markalar)
        self.assertEqual(rep["red"], [])
        self.assertEqual(self.brand("Verde Botanik")["status"], "candidate")

    def test_acilmayan_sayfa_kaynak_sagligina_yazilir(self):
        def getir(u):
            raise OSError("403 Forbidden")
        markalar, durum, _ = ajan.sayfa_cikar("https://www.rossmann.com.tr/x", getir, self._uret({}))
        self.assertEqual(markalar, [])
        self.assertFalse(durum["ok"])
        self.assertEqual(durum["source"], "rossmann.com.tr")

    def test_teyitte_yalniz_istenen_marka(self):
        cikti = {"markalar": [{"marka": "Verde Botanik", "urunler": [
            {"ad": "Onarıcı Balsam 50 ml", "fiyat": 1450, "alinti": "1.450 TL"}]}]}
        getir = lambda u: (u, SAYFA)
        sonuc = ajan.calistir("teyit", ara=None, getir=getir, uret=self._uret(cikti),
                              teyit=[{"brand": "Başka Marka", "source_url": "https://a.b/c"}])
        self.assertEqual(sonuc["brands"], [])
        sonuc = ajan.calistir("teyit", ara=None, getir=getir, uret=self._uret(cikti),
                              teyit=[{"brand": "Verde Botanik", "source_url": "https://a.b/c"}])
        self.assertEqual(len(sonuc["brands"]), 1)

    def test_json_ld_fiyati_dogrulanir(self):
        ham = ('<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",'
               '"name":"Nem Kremi 50 ml","brand":{"@type":"Brand","name":"Aqua Derm"},'
               '"offers":{"@type":"Offer","price":"1650.00","priceCurrency":"TRY"}}</script></head><body>'
               + "<p>JavaScript ile yüklenen sayfa iskeleti</p>" * 10 + "</body></html>")
        cikti = {"markalar": [{"marka": "Aqua Derm", "urunler": [
            {"ad": "Nem Kremi 50 ml", "kategori": "yuz", "fiyat": 1650, "alinti": "Fiyat: 1650.00 TRY"}]}]}
        markalar, durum, red = ajan.sayfa_cikar("https://aquaderm.com.tr/nem", lambda u: (u, ham), self._uret(cikti))
        self.assertTrue(durum["ok"])
        self.assertIn("price", [o["kind"] for o in markalar[0]["observations"]])
        self.assertEqual(red, 0)

    def test_odak_fiyat_bolumunu_secer(self):
        t = "menü " * 3000 + " Krem A 1.450,00 TL Krem B 990 TL " + "alt " * 500
        self.assertIn("1.450,00 TL", ajan.odak(t, 2000))

    def test_liste_sayfasi_modelsiz(self):
        metin = "\n".join(["Kategorinin Öne Çıkanları", "Isana", "El Kremi Çok Kuru Cilt, %5 Üre 100 ml", "TL", "175,00",
                           "TL", "Rossmann Card ile", "TL", "109,00", "TL", "Sepete Ekle", "Bilinmeyen Marka",
                           "Krem 50 ml", "TL", "99,00"])
        bs = ajan.liste_cikar(metin, {"isana"}, "https://www.rossmann.com.tr/cilt-bakimi")
        self.assertEqual([b["name"] for b in bs], ["Isana"])
        fiyat = [o for o in bs[0]["observations"] if o["kind"] == "price"]
        self.assertEqual([o["value"] for o in fiyat], [175.0])          # kart fiyatı ayrı ürün sanılmaz
        self.assertTrue(ajan.alinti_var(fiyat[0]["excerpt"], metin))
        self.assertEqual(self.run_ingest(bs)["red"], [])

    def test_tarayici_coker_duz_sayfaya_doner(self):
        duz = lambda u: (u, "<p>afiş 2000 TL ve üzeri kargo bedava</p>")
        def coken(u):
            raise RuntimeError("BrowserType.launch: Target page, context or browser has been closed")
        def engel(u):
            raise OSError("HTTP 403 (tarayıcı)")
        self.assertEqual(ajan.akilli_getir("https://a.b/c", duz, coken)[0], "https://a.b/c")
        with self.assertRaises(OSError):
            ajan.akilli_getir("https://a.b/c", duz, engel)

    def test_kesik_json_onarilir(self):
        v = ajan.json_ayikla('{"markalar": [{"marka": "A", "urunler": []}, {"marka": "B", "urun')
        self.assertEqual(v["markalar"][0], {"marka": "A", "urunler": []})
        self.assertNotIn("urunler", v["markalar"][-1] if len(v["markalar"]) > 1 else {})

    def test_tarama_arama_hatasini_raporlar(self):
        def ara(s):
            raise RuntimeError("GEMINI_API_KEY yok")
        sonuc = ajan.calistir("tarama", ara=ara, getir=None, uret=None, sorgu_adedi=2)
        arama = [d for d in sonuc["source_status"] if d["source"] == "gemini-arama"]
        self.assertEqual(len(arama), 2)
        self.assertFalse(any(d["ok"] for d in sonuc["source_status"]))


if __name__ == "__main__":
    unittest.main()
