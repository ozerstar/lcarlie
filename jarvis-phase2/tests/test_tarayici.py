# -*- coding: utf-8 -*-
"""Tarayıcı işi kapılarının testleri.

🔴 BU TESTLER NE VERİTABANINA NE AĞA ÇIKAR. Hepsi, bir isteğin kuyruğa
   GİRMESİNİ DURDURAN kapıları kanıtlar. Bir kapı sessizce gevşerse
   mevzuata aykırı bir istem ChatGPT'ye gider ya da kapı sunucuda keyfi
   dosya okuma aracına dönüşür.

Kuyruğun kendi kuralları (atomik kiralama, deneme tavanı,
INSAN_GEREKLI'nin terminal oluşu) veritabanındadır ve orada ÖLÇÜLDÜ;
burada tekrar edilmez -- iki yerde iki tanım, bu projede yaşanmış bir
hata sınıfı.
"""
import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

from jarvis import tarayici, tarayici_yedek

KOK = Path(__file__).resolve().parent.parent


def _kapi_modulu():
    """`tarayici-kapi` bir betik; modül olarak yüklenir.

    İki yerde durabilir: depodaki kaynak (`deploy/bin/`) ve kurulu
    hâli (`/opt/lcarlie/bin/`). Test ikisini de arar -- yalnız birine
    bağlanmak, testi kurulum düzenine bağımlı kılardı.
    """
    adaylar = [KOK / "deploy" / "bin" / "tarayici-kapi",
               Path("/opt/lcarlie/bin/tarayici-kapi")]
    yol = next((a for a in adaylar if a.is_file()), None)
    if yol is None:
        raise unittest.SkipTest(
            "tarayici-kapi bulunamadi: " + ", ".join(str(a) for a in adaylar))
    spec = importlib.util.spec_from_loader(
        "tarayici_kapi", loader=importlib.machinery.SourceFileLoader(
            "tarayici_kapi", str(yol)))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class HedefVeUzunlukKapisi(unittest.TestCase):
    def test_bilinmeyen_hedef_kabul_edilmez(self):
        for hedef in ("", None, "gemini_chat", "CLAUDE_CHAT", "claude chat"):
            with self.subTest(hedef=hedef):
                with self.assertRaises(tarayici.TarayiciHatasi):
                    tarayici.enqueue_browser_task("yeterince uzun bir istem", hedef)

    def test_cok_kisa_istem_kabul_edilmez(self):
        for istem in ("", "   ", "kisa"):
            with self.subTest(istem=istem):
                with self.assertRaises(tarayici.TarayiciHatasi):
                    tarayici.enqueue_browser_task(istem, "claude_chat")

    def test_cok_uzun_istem_kabul_edilmez(self):
        with self.assertRaises(tarayici.TarayiciHatasi):
            tarayici.enqueue_browser_task("a" * (tarayici.EN_COK_ISTEM + 1),
                                          "claude_chat")

    def test_istem_siniri_tablodaki_CHECK_ile_ayni(self):
        # İki yerde iki farklı sayı olmasın: migration 037 de 8000 diyor.
        metin = (KOK / "migrations" / "037_tarayici_isi.sql").read_text(encoding="utf-8")
        self.assertIn("length(istem) <= %d" % tarayici.EN_COK_ISTEM, metin)

    def test_hedef_kumesi_tablodaki_CHECK_ile_ayni(self):
        metin = (KOK / "migrations" / "037_tarayici_isi.sql").read_text(encoding="utf-8")
        for hedef in tarayici.HEDEFLER:
            self.assertIn("'%s'" % hedef, metin)


class MevzuatKapisi(unittest.TestCase):
    """🔴 Kapı İKİ YÖNLÜ: girişte istem, çıkışta sonuç."""

    def test_girişte_iddia_iceren_istem_kuyruga_GIRMEZ(self):
        for istem in ("VIREON egzamayi tedavi eder, gorsel uret",
                      "Bu krem varis hastaligini iyilestirir diye metin yaz",
                      "lekeleri yok eder baslikli reklam hazirla"):
            with self.subTest(istem=istem):
                with self.assertRaises(tarayici.UyumEngelledi) as kutu:
                    tarayici.enqueue_browser_task(istem, "chatgpt_image")
                self.assertTrue(kutu.exception.bulgular,
                                "engellendi ama hangi kuralla engellendigi yazilmamis")

    def test_cikista_iddia_iceren_sonuc_BLOKLU_isaretlenir(self):
        sonuc = tarayici.sonuc_uyum("Bu krem egzamayi tedavi eder.")
        self.assertEqual(sonuc["uyum_durumu"], "BLOKLU")
        self.assertTrue(sonuc["bloklu"])

    def test_temiz_sonuc_GECTI(self):
        sonuc = tarayici.sonuc_uyum("Cildi nemlendirmeye yardımcı olur.")
        self.assertEqual(sonuc["uyum_durumu"], "GECTI")
        self.assertEqual(sonuc["kapi"], "ISLETILDI")

    def test_metin_YOKSA_gecti_demek_YANLIS_olur(self):
        """Denetlenecek bir şey yoksa "geçti" demek yanlıştır: kapı
        işletilmedi, çünkü işletilecek metin yok. İkisi ayrı yazılır."""
        for bos in ("", "   ", None):
            with self.subTest(deger=bos):
                sonuc = tarayici.sonuc_uyum(bos)
                self.assertEqual(sonuc["kapi"], "METIN_YOK")
                self.assertEqual(sonuc["bloklu"], [])

    def test_uyum_notu_onay_vaat_etmez(self):
        """Kademe 1 temiz çıkması yayın onayı DEĞİLDİR; not bunu söyler."""
        sonuc = tarayici.sonuc_uyum("Cildi nemlendirir.")
        self.assertIn("insana ait", sonuc["not"])


class GirdiDosyasiKapisi(unittest.TestCase):
    """🔴 Kapı, sunucuda keyfi dosya okuma aracına DÖNÜŞEMEZ."""

    def test_izinli_koklerin_disi_reddedilir(self):
        for yol in ("/etc/passwd", "/root/.ssh/id_ed25519",
                    "/opt/lcarlie/n8n/.env", "/opt/lcarlie/alarm.log"):
            with self.subTest(yol=yol):
                with self.assertRaises(tarayici.TarayiciHatasi):
                    tarayici._girdi_dogrula([yol])

    def test_yol_kacisi_reddedilir(self):
        with self.assertRaises(tarayici.TarayiciHatasi):
            tarayici._girdi_dogrula(
                ["/opt/lcarlie/tarayici-cikti/../../../etc/passwd"])

    def test_goreli_yol_reddedilir(self):
        with self.assertRaises(tarayici.TarayiciHatasi):
            tarayici._girdi_dogrula(["urun-ham/a.jpg"])

    def test_izinli_kok_kabul_edilir(self):
        temiz = tarayici._girdi_dogrula(["/opt/lcarlie/urun-ham/a.jpg"])
        self.assertEqual(temiz, ["/opt/lcarlie/urun-ham/a.jpg"])

    def test_cok_fazla_dosya_reddedilir(self):
        with self.assertRaises(tarayici.TarayiciHatasi):
            tarayici._girdi_dogrula(
                ["/opt/lcarlie/urun-ham/%d.jpg" % i for i in range(7)])

    def test_bos_liste_sorun_degil(self):
        self.assertEqual(tarayici._girdi_dogrula(None), [])
        self.assertEqual(tarayici._girdi_dogrula([]), [])


class KapiDogrulayicilari(unittest.TestCase):
    """SSH kapısının argüman doğrulayıcıları."""

    @classmethod
    def setUpClass(cls):
        cls.kapi = _kapi_modulu()

    def test_is_id_sadece_tam_sayi(self):
        for deger in ("1; DROP TABLE core.tarayici_isi", "-1", "1.5", "",
                      "abc", "1 OR 1=1"):
            with self.subTest(deger=deger):
                with self.assertRaises(self.kapi.KapiHatasi):
                    self.kapi.is_kimligi(deger)
        self.assertEqual(self.kapi.is_kimligi("42"), 42)

    def test_jeton_sadece_uuid(self):
        for deger in ("", "not-a-uuid", "0" * 40, None):
            with self.subTest(deger=deger):
                with self.assertRaises(self.kapi.KapiHatasi):
                    self.kapi.jeton(deger)
        self.assertEqual(
            self.kapi.jeton("0aac7905-0c40-41de-88e6-e2d54527e5c5"),
            "0aac7905-0c40-41de-88e6-e2d54527e5c5")

    def test_worker_adi_desenli(self):
        for deger in ("", "a" * 81, "worker;rm -rf /", "worker adi", "../x"):
            with self.subTest(deger=deger):
                with self.assertRaises(self.kapi.KapiHatasi):
                    self.kapi.worker_adi(deger)
        self.assertEqual(self.kapi.worker_adi("pc1-chrome"), "pc1-chrome")

    def test_dosya_adi_YOL_ICERMEZ(self):
        """🔴 Basename'e indirip kabul etmek YETMEZ, REDDETMEK gerekir.

        İlk hâlinde `../../../etc/kotu.png` basename'e indirgenip
        sessizce kabul ediliyordu. Yazma güvenliydi ama düzgün bir
        worker asla yol göndermez: gönderdiyse ya kusurlu ya ele
        geçmiştir ve bu işaret silinmemeli.
        """
        for ad in ("../../../etc/kotu.png", "/etc/kotu.png",
                   "alt/dizin/x.png", "..\\x.png"):
            with self.subTest(ad=ad):
                with self.assertRaises(self.kapi.KapiHatasi):
                    self.kapi.dosya_yaz(1, ad, b"x")

    def test_izinli_olmayan_alt_komut_yok(self):
        """Kapı sabit bir listeden çalışır; kabuk komutu geçmez."""
        for ad in ("rm", "cat", "bash", "docker", "psql", "", "AL"):
            with self.subTest(ad=ad):
                self.assertNotIn(ad, self.kapi.KOMUTLAR)
        self.assertEqual(sorted(self.kapi.KOMUTLAR),
                         ["al", "bitir", "girdi", "hata", "insan", "nabiz"])

    def test_b64_tavanlari_zorunlu(self):
        import base64
        buyuk = base64.b64encode(b"x" * (self.kapi.EN_COK_DOSYA + 1)).decode()
        with self.assertRaises(self.kapi.KapiHatasi):
            self.kapi.coz_b64(buyuk, self.kapi.EN_COK_DOSYA, "dosya")
        with self.assertRaises(self.kapi.KapiHatasi):
            self.kapi.coz_b64("bu base64 degil!!", 100, "dosya")
        with self.assertRaises(self.kapi.KapiHatasi):
            self.kapi.coz_b64("", 100, "dosya")


class NabizSozlugu(unittest.TestCase):
    """🔴 BAYAT, makinenin KAPALI olduğunu KANITLAMAZ."""

    def test_esik_sistem_py_ile_ayni(self):
        # webconsole/sistem.py 180 sn kullanır; buradaki 300 sn ondan
        # DAHA GEVŞEKtir ve bu bilinçli: worker dakikada bir nabız atar,
        # bir atlama yanlış alarm üretmemeli. Yine de ikisinin ilişkisi
        # testle sabitlenir ki biri sessizce diğerinin altına düşmesin.
        self.assertGreaterEqual(tarayici.NABIZ_BAYAT_ESIGI_S, 180.0)

    def test_bayat_sebebi_teshis_DEGIL_gozlem(self):
        """Sebep cümlesi "kapalı" demez; iki olasılığı birden söyler."""
        kaynak = (KOK / "jarvis" / "tarayici.py").read_text(encoding="utf-8")
        self.assertIn("ag da takilmis olabilir", kaynak)

    def test_durum_sozlugu_sabit(self):
        kaynak = (KOK / "jarvis" / "tarayici.py").read_text(encoding="utf-8")
        for kelime in ("TAZE", "BAYAT", "RAPOR_YOK", "OKUNAMADI"):
            self.assertIn('"%s"' % kelime, kaynak)


class YedekYol(unittest.TestCase):
    def test_bilinmeyen_hedefin_yedegi_yok(self):
        with self.assertRaises(tarayici_yedek.YedekYok):
            tarayici_yedek.dene("yok_boyle", "istem")

    def test_kapaliyken_yedek_calismaz(self):
        eski = tarayici_yedek.YEDEK_ACIK
        tarayici_yedek.YEDEK_ACIK = False
        try:
            with self.assertRaises(tarayici_yedek.YedekYok):
                tarayici_yedek.dene("claude_chat", "istem")
        finally:
            tarayici_yedek.YEDEK_ACIK = eski

    def test_her_hedefin_yedegi_TANIMLI(self):
        """Tanımlı olmak çalışmak DEĞİLDİR; çalışmayan yedek çalışma
        anında sebebiyle reddedilir (bkz. görsel yedeği)."""
        self.assertEqual(set(tarayici_yedek.YEDEKLER), set(tarayici.HEDEFLER))

    def test_gorsel_yedegi_OLU_KUYRUGA_YAZMAZ(self):
        """🔴 PC-2 raporu bayatsa kuyruğa yazıp 'yedek çalıştı' demek,
        işi kimsenin bakmadığı yere atıp başarılı saymak olurdu."""
        kaynak = (KOK / "jarvis" / "tarayici_yedek.py").read_text(encoding="utf-8")
        self.assertIn("KUYRUĞA YAZIP", kaynak)
        self.assertIn('durum != "TAZE"', kaynak)


class SozlesmeEslemesi(unittest.TestCase):
    def test_TARAYICI_SONUC_yeni_DB_tipi_UYDURMAZ(self):
        from jarvis.action_contract import INTENT_TO_CANONICAL
        self.assertEqual(INTENT_TO_CANONICAL["TARAYICI_SONUC"],
                         "REQUEST_HUMAN_REVIEW")


if __name__ == "__main__":
    unittest.main()
