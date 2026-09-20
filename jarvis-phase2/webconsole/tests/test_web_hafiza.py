"""HAFIZA ekrani ve /api/hafiza uclari.

NEDEN VAR
Kisisel asistan katmani (jarvis.conversation_memory + jarvis.hatira)
20.09.2026'da kuruldu, calisiyordu ve panelde HICBIR yuzu yoktu -- ne
ekran, ne uc nokta. Kimse fark etmedi cunku hicbir sey hata vermiyordu:
yetenek sessizce yoktu. Ayni sinif hata bu projede daha once de yasandi
(jarvis/knowledge.py uretime hic kopyalanmamisti). Bu testler o yuzden
"uc nokta cevap veriyor mu" ile yetinmez, ekranin ONU CAGIRDIGINI da
olcer.

Bu suite uretim PostgreSQL'ine dokunmaz: DB katmani mocklanir, not dosyasi
gecici bir JARVIS_STATE_DIR altinda durur ve arama dizini (mem0) hic
cagrilmaz -- conversation_memory zaten gercek state dizini disinda dizini
kapatiyor.
"""
import http.client
import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent.parent
JARVIS_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JARVIS_ROOT))

import os  # noqa: E402
os.environ["JARVIS_ENABLED"] = "true"
os.environ["JARVIS_MODE"] = "SHADOW"
os.environ["EXTERNAL_ACTIONS"] = "false"
os.environ["JARVIS_MEMORY_TRANSPORT"] = "local-docker"

import auth  # noqa: E402

TMP_STATE = Path(tempfile.mkdtemp())
os.environ["JARVIS_WEB_STATE_DIR"] = str(TMP_STATE)
os.environ["JARVIS_STATE_DIR"] = str(TMP_STATE)
os.environ["JARVIS_WEB_INSECURE_COOKIES"] = "1"
auth.AUTH_FILE = TMP_STATE / "auth.json"

with patch("jarvis.memory.CompanyMemory.__init__", return_value=None), \
     patch("jarvis.operator.OperatorSession.__init__", return_value=None):
    import app  # noqa: E402

from jarvis import conversation_memory as _cmem  # noqa: E402

STATIC = HERE / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")

TEST_USER = "test-operator"
TEST_PASS = "correct horse battery staple 42"


class HafizaApiTests(unittest.TestCase):
    """Uc noktalarin gercek HTTP davranisi."""

    @classmethod
    def setUpClass(cls):
        auth.set_password(TEST_USER, TEST_PASS)
        app._memory = MagicMock()
        app._operator = MagicMock()
        app._shadow_runner = MagicMock()
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        app.sessions = auth.SessionStore()
        app.throttle = auth.LoginThrottle()
        # Her test temiz bir not dosyasiyla baslar. Yol MODULDEN sorulur,
        # TMP_STATE'ten TURETILMEZ: discover butun test dosyalarini tek
        # surecte calistiriyor ve conversation_memory bir kez, hangi
        # modul once JARVIS_STATE_DIR'i ayarladiysa ona gore iceri
        # aliniyor. Yolu burada varsaymak, silmedigimiz bir dosyayi
        # sildigimizi sanmak demekti -- bir kez oldu, notlar testler
        # arasinda birikti.
        notes = _cmem._path("operator", "notes")
        if notes.exists():
            notes.unlink()
        self.csrf, self.sid = self._login()

    def _req(self, method, path, payload=None, auth_headers=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"Content-Type": "application/json"}
            if auth_headers:
                headers["Cookie"] = f"{app.SESSION_COOKIE}={self.sid}"
                headers["X-CSRF-Token"] = self.csrf
            body = json.dumps(payload) if payload is not None else None
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            return resp, (json.loads(data) if data else {})
        finally:
            conn.close()

    def _login(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/login",
                         body=json.dumps({"username": TEST_USER, "password": TEST_PASS}),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            body = json.loads(resp.read())
            sid = None
            for part in ", ".join(resp.msg.get_all("Set-Cookie") or []).split(","):
                part = part.strip()
                if part.startswith(app.SESSION_COOKIE + "="):
                    sid = part.split(";")[0].split("=", 1)[1]
            return body["csrf_token"], sid
        finally:
            conn.close()

    # -- yetki ----------------------------------------------------------
    def test_hafiza_oturumsuz_okunamaz(self):
        resp, _ = self._req("GET", "/api/hafiza", auth_headers=False)
        self.assertEqual(resp.status, 401)

    def test_not_eklemek_csrf_ister(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/hafiza", body=json.dumps({"note": "x"}),
                         headers={"Content-Type": "application/json",
                                  "Cookie": f"{app.SESSION_COOKIE}={self.sid}"})
            self.assertEqual(conn.getresponse().status, 403)
        finally:
            conn.close()

    # -- okuma ----------------------------------------------------------
    def test_bos_hafiza_bos_liste_doner_hata_degil(self):
        resp, body = self._req("GET", "/api/hafiza")
        self.assertEqual(resp.status, 200)
        self.assertEqual(body["notlar"], [])

    def test_dosya_ve_dizin_AYRI_raporlanir(self):
        """Tek sayiya indirmek, dizin coktugunde paneli yalanci yapardi."""
        _, body = self._req("GET", "/api/hafiza")
        self.assertIn("dosya", body)
        self.assertIn("dizin", body)
        self.assertIn("kurulu", body["dizin"])

    def test_yanit_kaynak_sinirini_soyler(self):
        _, body = self._req("GET", "/api/hafiza")
        self.assertIn("dizin", body["uyari"].lower())
        self.assertEqual(body["sinir"], 60)

    # -- yazma ----------------------------------------------------------
    def test_not_eklenir_ve_geri_okunur(self):
        resp, body = self._req("POST", "/api/hafiza",
                               {"note": "Toplu fiyatı yüzde bazlı istiyorum."})
        self.assertEqual(resp.status, 200)
        self.assertEqual([n["note"] for n in body["notlar"]],
                         ["Toplu fiyatı yüzde bazlı istiyorum."])
        _, tekrar = self._req("GET", "/api/hafiza")
        self.assertEqual(len(tekrar["notlar"]), 1)

    def test_bos_not_reddedilir(self):
        resp, _ = self._req("POST", "/api/hafiza", {"note": "   "})
        self.assertEqual(resp.status, 400)

    def test_notlar_en_yeni_ustte_ve_zaman_damgali(self):
        self._req("POST", "/api/hafiza", {"note": "birinci"})
        _, body = self._req("POST", "/api/hafiza", {"note": "ikinci"})
        self.assertEqual([n["note"] for n in body["notlar"]], ["ikinci", "birinci"])
        self.assertTrue(body["notlar"][0]["at"], "not zaman damgasiz kaydedilmis")

    def test_ayni_not_iki_kez_birikmez(self):
        self._req("POST", "/api/hafiza", {"note": "aynı cümle"})
        _, body = self._req("POST", "/api/hafiza", {"note": "aynı cümle"})
        self.assertEqual(len(body["notlar"]), 1)

    # -- silme ----------------------------------------------------------
    def test_silinen_sayisi_SUNUCUDAN_doner(self):
        """Parcaya gore silmek birden fazla notu goturebilir; kac tane
        gittigini panel tahmin etmemeli, sunucu soylemeli."""
        self._req("POST", "/api/hafiza", {"note": "VIREON fiyatı"})
        self._req("POST", "/api/hafiza", {"note": "VIREON fiyatı kesinleşti"})
        resp, body = self._req("POST", "/api/hafiza/sil", {"fragment": "VIREON fiyatı"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(body["silinen"], 2)
        self.assertEqual(body["notlar"], [])

    def test_eslesmeyen_parca_sifir_doner_hata_degil(self):
        self._req("POST", "/api/hafiza", {"note": "bir not"})
        resp, body = self._req("POST", "/api/hafiza/sil", {"fragment": "hiç yok"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(body["silinen"], 0)
        self.assertEqual(len(body["notlar"]), 1)

    def test_bos_parca_ile_silinmez(self):
        """Bos parca her notla eslesirdi -- tek tusla hafizayi silmek."""
        self._req("POST", "/api/hafiza", {"note": "korunmali"})
        resp, _ = self._req("POST", "/api/hafiza/sil", {"fragment": ""})
        self.assertEqual(resp.status, 400)
        _, body = self._req("GET", "/api/hafiza")
        self.assertEqual(len(body["notlar"]), 1)


class HafizaEkraniTests(unittest.TestCase):
    """Uc nokta calissa bile ekran onu CAGIRMIYORSA yetenek yine yoktur."""

    def test_menude_ve_gorunum_haritasinda(self):
        self.assertRegex(INDEX, r'<button[^>]*data-view="hafiza"[^>]*>')
        self.assertNotIn("disabled", re.search(
            r'<button[^>]*data-view="hafiza"[^>]*>', INDEX).group(0))
        self.assertRegex(APP_JS, r"hafiza:\s*'viewHafiza'")
        self.assertIn('id="viewHafiza"', INDEX)

    def test_sekme_acilinca_gercekten_yukleniyor(self):
        setview = APP_JS[APP_JS.index("function setView("):]
        setview = setview[:setview.index("\n}")]
        self.assertIn("loadHafiza()", setview)

    def test_istekler_api_yardimcisindan_gecer(self):
        """Ham fetch 401'i yakalamaz; panel 'hata' der, oysa oturum dusmustur."""
        kaynak = APP_JS[APP_JS.index("async function loadHafiza"):]
        self.assertIn("await api('/api/hafiza')", kaynak)
        self.assertNotIn("fetch('/api/hafiza", kaynak)

    def test_iki_kaynak_ekranda_da_ayri(self):
        kaynak = APP_JS[APP_JS.index("function hfDurumCiz"):]
        kaynak = kaynak[:kaynak.index("\nfunction hfListeCiz")]
        self.assertIn("data.dizin", kaynak)
        self.assertIn("data.dosya", kaynak)
        self.assertIn("ERİŞİLEMİYOR", kaynak)

    def test_tutarlilik_kararini_ekran_vermez(self):
        """Iki sayiyi tarayicida kiyaslamak, sunucunun bildigi seyi ikinci
        kez -- ve baska turlu -- hesaplamak olurdu."""
        kaynak = APP_JS[APP_JS.index("function hfDurumCiz"):]
        kaynak = kaynak[:kaynak.index("\nfunction hfListeCiz")]
        self.assertIn("data.tutarli === false", kaynak)

    def test_silinen_sayisi_ekranda_uretilmez(self):
        kaynak = APP_JS[APP_JS.index("function hfBind"):]
        self.assertIn("body.silinen", kaynak)

    def test_silme_iki_adimli(self):
        """Tek tikla geri alinamaz bir kayit silinmemeli."""
        kaynak = APP_JS[APP_JS.index("function hfBind"):]
        self.assertIn("EMİN MİSİNİZ?", kaynak)

    def test_ekran_cikarim_yaptigini_iddia_etmez(self):
        """Hafizaya yalniz operatorun yazdigi cumle girer; arayuz bunu
        soylemek zorunda, cunku aksini varsayan bir operator sohbette
        soyledigi seyin hatirlandigini sanir."""
        self.assertIn("çıkarım yapılarak eklenmez", INDEX)


if __name__ == "__main__":
    unittest.main()
