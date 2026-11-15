"""K1/K2 (15.11.2026): satış ve stok tek kaynak SQL sözleşmesi.

Veritabanına bağlanmaz; yayınlanan SQL kaynağını (pc/n8n-kaynak) okur. Davranış
testi ayrıca DB'de: pc/n8n-kaynak/satis-stok-test.sql (BEGIN/ROLLBACK, 25 kontrol).

Kilitlenenler:
- reklam sayfasının okuduğu biçim: satis_urun_gunluk (gun, kanal, barkod, kod, siparis,
  adet, ciro), satis_kanal_gunluk (gun, kanal, siparis, ciro), satis_tazelik (son_olcum)
- Trendyol nöbetçi tutarı (liste fiyatı) ciro DEĞİL
- sipariş başına kaynak önceliği (finans > alıcı > nöbetçi) ve iptal hariç
- kâr zinciri tüm kanallardan okur; stok hiçbir yere yazmaz
- panel rolü yeni görünümleri okuyabilir
"""
import re
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
SQL = KOK / "pc" / "n8n-kaynak"


def _oku(ad):
    return (SQL / ad).read_text(encoding="utf-8")


def _gorunum(metin, ad):
    # gövde bir sonraki COMMENT/CREATE'e kadar (yorumlardaki ';' gövdeyi kesmesin)
    m = re.search(r"CREATE (?:OR REPLACE )?VIEW %s AS(.*?)\n(?:COMMENT ON VIEW|CREATE )" % re.escape(ad), metin, re.S)
    if not m:
        raise AssertionError("görünüm yok: " + ad)
    return m.group(1)


class SatisTekKaynak(unittest.TestCase):
    def setUp(self):
        self.marj = _oku("mart-marj.sql")
        self.kalem = _gorunum(self.marj, "mart.satis_kalem_tum")

    def test_reklam_bicimi_urun_gunluk(self):
        g = _gorunum(self.marj, "mart.satis_urun_gunluk")
        for sutun in ("k.gun", "k.kanal", "k.barkod", "AS kod", "AS siparis", "AS adet", "AS ciro"):
            self.assertIn(sutun, g)
        self.assertIn("ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')", g)  # iptal/ödenmemiş hariç

    def test_reklam_bicimi_kanal_gunluk_ve_tazelik(self):
        g = _gorunum(self.marj, "mart.satis_kanal_gunluk")
        for sutun in ("k.gun", "k.kanal", "AS siparis", "AS ciro"):
            self.assertIn(sutun, g)
        self.assertIn("AS son_olcum", _gorunum(self.marj, "mart.satis_tazelik"))

    def test_trendyol_liste_fiyati_ciro_degil(self):
        self.assertIn("LISTE_FIYATI_KULLANILMADI", self.kalem)
        self.assertRegex(self.kalem, r"CASE WHEN p\.kanal <> 'trendyol' AND jsonb_array_length\(p\.kalemler\) = 1 THEN p\.tutar END")

    def test_kaynak_onceligi_cift_sayim_yok(self):
        self.assertIn("NOT (a.kanal = 'trendyol' AND a.siparis_no IN (SELECT order_no FROM cs_sip))", self.kalem)
        self.assertIn("NOT EXISTS (SELECT 1 FROM core.alici_siparis a WHERE a.kanal = p.kanal AND a.siparis_no = p.siparis_no)", self.kalem)
        self.assertIn("DISTINCT ON (p.kanal, p.siparis_no)", self.kalem)          # paket tekrarı tek
        self.assertIn("NOT EXISTS (SELECT 1 FROM raw.wix_order w WHERE w.siparis_no::text = a.siparis_no)", self.kalem)

    def test_lcarlie_disi_ve_klinik_satisi_girmez(self):
        self.assertIn("c.business = 'lcarlie'", self.kalem)
        self.assertIn("LIKE '868486960%'", self.kalem)

    def test_komisyon_uydurulmaz_ve_wix_pos(self):
        self.assertIn("core.urun_platform_komisyon", self.kalem)
        self.assertNotRegex(self.kalem, r"coalesce\(z\.pazaryeri_yuzde")      # yoksa NULL kalır
        self.assertIn("'POS_KOMISYONU'", self.kalem)
        self.assertIn("WHEN z.odeme_yontemi IS NULL THEN NULL", self.kalem)

    def test_kar_zinciri_tum_kanallardan(self):
        for ad in ("mart.urun_karlilik", "mart.gunluk_marj", "mart.maliyet_eksik"):
            self.assertIn("mart.satis_kalem_tum", _gorunum(self.marj, ad), ad)
        eko = _oku("cogs-truth-sema.sql")
        self.assertIn("FROM mart.satis_kalem_tum k GROUP BY k.siparis_id", eko)
        self.assertIn("giden_kargo(pazaryeri kesintisi VERI_YOK)", eko)
        self.assertIn("CREATE OR REPLACE FUNCTION core.bilesen_bul", eko)   # DROP edilirse yayın kırılır
        self.assertNotIn("DROP FUNCTION IF EXISTS core.bilesen_bul(text, timestamptz);\nCREATE", eko)

    def test_stok_yazmaz_ve_siraya_girdi(self):
        stok = _oku("stok-tek-kaynak.sql")
        govde = re.sub(r"--[^\n]*", "", stok).upper()
        for yasak in ("INSERT ", "UPDATE ", "DELETE "):
            self.assertNotIn(yasak, govde)
        sira = _oku("raw-uygula.sh")
        self.assertLess(sira.index("mart-marj.sql"), sira.index("stok-tek-kaynak.sql"))

    def test_panel_rolu_yetkisi(self):
        self.assertRegex(self.marj, r"GRANT SELECT ON mart\.satis_kalem_tum, mart\.satis_kanal_gunluk, mart\.satis_urun_gunluk,\s+mart\.satis_tazelik")
        self.assertIn("GRANT SELECT ON core.ayar TO jarvis_web", self.marj)
        self.assertIn("GRANT SELECT ON core.stok_guncel, core.stok_tutarsizlik TO jarvis_web", _oku("stok-tek-kaynak.sql"))

    def test_dorsivia_wix_degeri(self):
        tohum = _oku("urun-maliyet-finans.sql")
        satir = [s for s in tohum.splitlines() if "'Dorsivia'" in s][0]
        self.assertIn("'8684869609400', '13346719', '8684869609400'", satir)


if __name__ == "__main__":
    unittest.main()
