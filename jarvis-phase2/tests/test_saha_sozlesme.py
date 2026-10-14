# -*- coding: utf-8 -*-
"""SAHA sözleşmesi: tür listesi, anahtar çözümü, harita sınırları.

🔴 BU DOSYANIN VAR OLMA SEBEBİ ÖLÇÜLMÜŞ BİR HATADIR. `saha.TURLER` altı tür
yazıyordu, veride on altı vardı. Filtre beyaz listeden geçmeyen değeri
SESSİZCE düşürüyordu: koşul hiç eklenmiyor, sorgu filtresiz dönüyordu.
Kullanıcı "HUZUREVİ seçtim" diyor, ekran 18.845 kayıt gösteriyor ve ikisi de
doğru görünüyordu. Aşağıdaki ilk sınama, tarama betiklerinin ürettiği
türlerle panelin tanıdığı türleri KARŞILAŞTIRIR; bir daha ayrışamazlar.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

import harita  # noqa: E402
import saha  # noqa: E402

BETIK = KOK / "scripts" / "overture-tara.py"


def _betikteki_turler() -> set[str]:
    """Overture tarayıcısının ürettiği tür adları."""
    metin = BETIK.read_text(encoding="utf-8")
    bas = metin.index("KATEGORI = [")
    son = metin.index("]", bas)
    return set(re.findall(r'"([A-Z_]{3,})"\s*\)', metin[bas:son]))


class TurListesiVeriyleAyniKalir(unittest.TestCase):
    def test_tarayicinin_urettigi_her_tur_panelde_taninir(self):
        eksik = _betikteki_turler() - set(saha.TURLER)
        self.assertEqual(eksik, set(),
                         "tarama bu türleri üretiyor ama saha.TURLER tanımıyor: "
                         "filtre onları SESSİZCE yok sayar")

    def test_her_turun_turkce_etiketi_var(self):
        eksik = [t for t in saha.TURLER if t not in saha.TUR_ETIKET]
        self.assertEqual(eksik, [], "etiketsiz tür ekranda ham anahtar görünür")

    def test_etiketler_ham_anahtar_degil(self):
        # "PSIKOLOG" yazmak etiket sayılmaz; ekranda okunacak ad istiyoruz.
        ayni = [t for t in saha.TURLER if saha.TUR_ETIKET[t] == t]
        self.assertEqual(ayni, [])


class ReddedilenDegerHataVerir(unittest.TestCase):
    """Sessizce düşmek, filtrenin işlediği yanılgısını üretir."""

    def test_bilinmeyen_tur_hata(self):
        with self.assertRaises(saha.SahaHatasi):
            saha._liste_kosulu("tur", ["YOKBOYLE"], set(saha.TURLER))

    def test_sql_kirinti_hata(self):
        with self.assertRaises(saha.SahaHatasi):
            saha._liste_kosulu("tur", ["A' OR '1'='1"], set(saha.TURLER))

    def test_gecerli_deger_kosul_uretir(self):
        kosul = saha._liste_kosulu("tur", ["ECZANE"], set(saha.TURLER))
        self.assertIn("'ECZANE'", kosul)

    def test_bos_liste_kosul_uretmez(self):
        self.assertEqual(saha._liste_kosulu("tur", [], set(saha.TURLER)), "")

    def test_gecersiz_ziyaret_durumu_hata(self):
        with self.assertRaises(saha.SahaHatasi):
            saha._kosul_parcalari(ziyaret_durumu="BELKI")


class UcKaynagInHepsineZiyaretYazilabilir(unittest.TestCase):
    """Hedeflerin %88'i 'ovt:' önekli; reddedilirse panel işe yaramaz."""

    def test_overture_anahtari_kabul(self):
        c = saha._anahtar_coz("ovt:08f1f0a2-3b4c-4d5e-8f90-112233445566")
        self.assertEqual(c["osm_tur"], "NULL")
        self.assertEqual(c["nokta_id"], "NULL")
        self.assertTrue(c["anahtar"].startswith("ovt:"))

    def test_osm_anahtari_eski_sutunlari_doldurur(self):
        c = saha._anahtar_coz("osm:node:12345")
        self.assertEqual(c["osm_tur"], "'node'")
        self.assertEqual(c["osm_id"], "12345")

    def test_elle_anahtari(self):
        self.assertEqual(saha._anahtar_coz("elle:7")["nokta_id"], "7")

    def test_bilinmeyen_onek_reddedilir(self):
        for kotu in ("", "foo:1", "osm:sehir:1", "osm:node:abc", "elle:x",
                     "ovt:kotu anahtar"):
            with self.assertRaises(saha.SahaHatasi, msg=kotu):
                saha._anahtar_coz(kotu)


class HaritaAcikVekilDegildir(unittest.TestCase):
    """Sınırsız karo ucu, dünyanın karosunu bizim üzerimizden indirtir."""

    def test_ankara_merkezi_kabul(self):
        harita.dogrula(14, *self._karo(39.925, 32.866, 14))

    def test_cerceve_disi_reddedilir(self):
        # İstanbul: aynı yakınlaştırmada Ankara çerçevesinin dışında.
        with self.assertRaises(harita.HaritaHatasi):
            harita.dogrula(14, *self._karo(41.008, 28.978, 14))

    def test_yakinlastirma_sinirli(self):
        for z in (0, 9, 19, 25):
            with self.assertRaises(harita.HaritaHatasi):
                harita.dogrula(z, 0, 0)

    @staticmethod
    def _karo(enlem, boylam, z):
        import math
        n = 2 ** z
        x = int((boylam + 180.0) / 360.0 * n)
        y = int((1.0 - math.asinh(math.tan(math.radians(enlem))) / math.pi) / 2.0 * n)
        return x, y


class ElemeGizlemekDegilIsaretlemektir(unittest.TestCase):
    def test_gecersiz_gorunum_hata(self):
        with self.assertRaises(saha.SahaHatasi):
            saha._temel("SACMA")

    def test_varsayilan_elenenleri_gizler(self):
        self.assertIn("NOT hedef_disi", saha._temel(None))

    def test_goster_elenenleri_de_getirir(self):
        self.assertNotIn("hedef_disi", saha._temel("GOSTER"))

    def test_sadece_yalniz_elenenler(self):
        self.assertIn("hedef_disi AND", saha._temel("SADECE"))


# --- Veritabanı gerektiren sınamalar ---------------------------------------
# Bunlar ölçüm sınamalarıdır: kod değil VERİ doğru mu diye bakarlar.
# Veritabanına ulaşılamıyorsa ATLANIR -- "atlandı" ile "geçti" ayrı şeylerdir.

def _db_var() -> bool:
    try:
        saha._oku("SELECT row_to_json(t) FROM (SELECT 1 AS x) t;")
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_db_var(), "veritabanina ulasilamadi")
class IlceListesiTemizKalir(unittest.TestCase):
    """Aynı ilçe dört ayrı seçenek olarak çıkıyordu: 'Çankaya' 7.955,
    'ÇANKAYA' 1, 'çankaya' 2, 'Cankaya' 2."""

    def setUp(self):
        self.ilceler = [i["deger"] for i in
                        saha.filtre_secenekleri().get("ilceler") or []]

    def test_ayni_ilce_tek_secenek(self):
        kucuk = [i.lower() for i in self.ilceler]
        self.assertEqual(len(kucuk), len(set(kucuk)),
                         "aynı ilçe birden fazla yazımla listede")

    def test_il_adi_ilce_diye_listelenmez(self):
        for yasak in ("Ankara", "ANKARA", "İç Anadolu Bölgesi"):
            self.assertNotIn(yasak, self.ilceler,
                             "il/bölge adı ilçe seçeneği olamaz")

    def test_baska_ilin_ilcesi_listelenmez(self):
        for yasak in ("Milas", "Nilüfer", "Şehitkamil"):
            self.assertNotIn(yasak, self.ilceler)

    def test_semt_ilce_diye_listelenmez(self):
        for yasak in ("Batıkent", "Çayyolu", "Ümitköy", "Çukurambar"):
            self.assertNotIn(yasak, self.ilceler)

    def test_hepsi_resmi_ankara_ilcesi(self):
        resmi = {
            "Akyurt", "Altındağ", "Ayaş", "Bala", "Beypazarı", "Çamlıdere",
            "Çankaya", "Çubuk", "Elmadağ", "Etimesgut", "Evren", "Gölbaşı",
            "Güdül", "Haymana", "Kahramankazan", "Kalecik", "Keçiören",
            "Kızılcahamam", "Mamak", "Nallıhan", "Polatlı", "Pursaklar",
            "Sincan", "Şereflikoçhisar", "Yenimahalle"}
        self.assertEqual(set(self.ilceler) - resmi, set())


@unittest.skipUnless(_db_var(), "veritabanina ulasilamadi")
class ElemeYanlisKaydiTutmaz(unittest.TestCase):
    """🔴 Kör bir 'oto' filtresi hekimi de elerdi."""

    def test_otomotiv_elendi(self):
        elenen = {h["ad"] for h in
                  saha.hedefler(eleme="SADECE", limit=100)["hedefler"]}
        self.assertIn("Imza Oto Kuaför", elenen)
        self.assertIn("Iskitler Oto Sanayi Sitesi", elenen)

    def test_soyadi_oto_olan_hekim_elenmedi(self):
        elenen = {h["ad"] for h in
                  saha.hedefler(eleme="SADECE", limit=100)["hedefler"]}
        self.assertNotIn("Prof Dr M Ali Oto", elenen)

    def test_plastik_cerrahi_lastik_sanilmadi(self):
        # 'lastik' kalıbı sınırsız yazılsaydı 'Plastik Cerrahi' eşleşirdi.
        for h in saha.hedefler(eleme="SADECE", limit=100)["hedefler"]:
            self.assertNotIn("lastik", (h["ad"] or "").lower().replace("plastik", ""))

    def test_elenen_kayit_silinmedi(self):
        self.assertGreater(saha.hedefler(eleme="SADECE", limit=5)["sayi"], 0)


@unittest.skipUnless(_db_var(), "veritabanina ulasilamadi")
class AramaAksanaTakilmaz(unittest.TestCase):
    """Türkçe karakteri olmayan klavyeden 'dis' yazan hiçbir şey bulamıyordu."""

    def test_aksansiz_yazim_bulur(self):
        r = saha.hedefler(arama="dis klinig", limit=5)
        self.assertGreater(r["sayi"], 0)

    def test_buyuk_harf_farki_onemsiz(self):
        a = saha.hedefler(arama="ECZANE", limit=50)["sayi"]
        b = saha.hedefler(arama="eczane", limit=50)["sayi"]
        self.assertEqual(a, b)

    def test_kecioren(self):
        self.assertGreater(saha.hedefler(arama="kecioren", limit=5)["sayi"], 0)


if __name__ == "__main__":
    unittest.main()
