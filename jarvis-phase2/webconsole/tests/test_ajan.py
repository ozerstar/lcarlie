"""Sohbet ajanının kapıları. Gerçek API çağrılmaz; istemci taklit edilir."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

os.environ.setdefault("JARVIS_STATE_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))
KOK = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KOK), str(KOK / "webconsole")]

import ajan  # noqa: E402
import chat  # noqa: E402
import conversation  # noqa: E402
from jarvis.memory import CompanyMemory  # noqa: E402


class Evidence:
    def __init__(self, records):
        self.records = records


class Memory:
    def __init__(self):
        self.okunan = []

    def _fetch(self, ad):
        self.okunan.append(ad)
        return Evidence([{"kanal": "trendyol", "tutar": 2560}] if ad != "sales_orders" else [])

    def get_system_status(self):
        return Evidence([{"pending_actions": 19}])


class SahteAkis:
    def __init__(self, olaylar, son):
        self.olaylar, self.son = olaylar, son

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self.olaylar)

    def get_final_message(self):
        return self.son


class Hatalar:
    class APIConnectionError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        pass


def istemci(turlar):
    """turlar: her model cagrisi icin (olaylar, son_mesaj) ya da firlatilacak istisna."""
    kuyruk = list(turlar)

    def akis(**_):
        tur = kuyruk.pop(0)
        if isinstance(tur, Exception):
            raise tur
        return SahteAkis(*tur)

    return NS(beta=NS(messages=NS(stream=akis)))


def arac_turu(ad, girdi):
    blok = NS(type="tool_use", id="tu1", name=ad, input=girdi)
    return ([], NS(stop_reason="tool_use", content=[blok], usage=NS(input_tokens=10, output_tokens=5)))


def metin_turu(*parcalar):
    return ([NS(type="text", text=p) for p in parcalar],
            NS(stop_reason="end_turn", content=[NS(type="text", text="".join(parcalar))],
               usage=NS(input_tokens=10, output_tokens=5)))


class AracTesti(unittest.TestCase):
    def test_sorgular_izinli_listede(self):
        self.assertTrue(set(ajan.SORGULAR) <= set(CompanyMemory.QUERIES))

    def test_bilinmeyen_sorgu_calismaz(self):
        mem = Memory()
        sonuc = ajan.arac_calistir(NS(id="x", name="sirket_verisi", input={"sorgu": "action_contract"}), mem)
        self.assertTrue(sonuc["is_error"])
        self.assertEqual(mem.okunan, [])

    def test_bilinmeyen_arac_calismaz(self):
        sonuc = ajan.arac_calistir(NS(id="x", name="fiyat_degistir", input={"urun": "VIREON"}), Memory())
        self.assertTrue(sonuc["is_error"])

    def test_bos_girdi_reddedilir(self):
        for ad, girdi in (("web_arastir", {"soru": "  "}), ("satis_ozeti", {}), ("sirket_bilgisi", "x")):
            self.assertFalse(ajan.gecerli_girdi(ad, girdi), ad)

    def test_arac_hatasi_sohbeti_durdurmaz(self):
        class Bozuk(Memory):
            def get_system_status(self):
                raise RuntimeError("db yok")
        sonuc = ajan.arac_calistir(NS(id="x", name="bekleyen_onaylar", input={}), Bozuk())
        self.assertTrue(sonuc["is_error"])
        self.assertIn("RuntimeError", sonuc["content"])

    def test_bekleyen_onay(self):
        sonuc = ajan.arac_calistir(NS(id="x", name="bekleyen_onaylar", input={}), Memory())
        self.assertIn("19 öneri", sonuc["content"])


class GecmisTesti(unittest.TestCase):
    def test_sira_ve_son_soru(self):
        gecmis = [{"role": "assistant", "content": "yetim cevap"},
                  {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
                  {"role": "assistant", "content": "c"}, {"role": "user", "content": "cevapsiz"}]
        m = ajan.gecmis_mesajlar(gecmis, "yeni soru")
        self.assertEqual([x["role"] for x in m], ["user", "assistant", "user"])
        self.assertEqual(m[0]["content"], "a\n\nb")
        self.assertEqual(m[-1]["content"], "yeni soru")


class DonguTesti(unittest.TestCase):
    def calistir(self, turlar):
        with patch.object(ajan, "_istemci", return_value=(Hatalar, istemci(turlar))), \
             patch.object(ajan, "_kaydet"):
            return list(ajan.stream("bekleyen onay var mi", Memory()))

    def test_arac_sonra_cevap(self):
        cerceveler = self.calistir([arac_turu("bekleyen_onaylar", {}), metin_turu("19 ", "öneri bekliyor.")])
        turler = [c["type"] for c in cerceveler]
        self.assertEqual(turler[0], "stage")
        self.assertIn("Bekleyen onaylara bakıyorum", [c.get("label") for c in cerceveler])
        self.assertEqual([c["delta"] for c in cerceveler if c["type"] == "token"], ["19 ", "öneri bekliyor."])
        sonuc = cerceveler[-1]["result"]
        self.assertEqual(sonuc["answer"], "19 öneri bekliyor.")
        self.assertEqual(sonuc["araclar"], ["bekleyen_onaylar"])
        self.assertEqual(sonuc["external_actions"], 0)

    def test_baslamadan_hata_geri_donus_ister(self):
        with self.assertRaises(ajan.AjanKullanilamaz):
            self.calistir([Hatalar.APIConnectionError("yok")])

    def test_uretimden_sonra_hata_cevaba_yazilir(self):
        cerceveler = self.calistir([arac_turu("bekleyen_onaylar", {}), Hatalar.APIStatusError("500")])
        self.assertIn("yarım kalmış", cerceveler[-1]["result"]["answer"])

    def test_tur_siniri(self):
        cerceveler = self.calistir([arac_turu("bekleyen_onaylar", {})] * ajan.EN_FAZLA_TUR)
        self.assertIn("turu sınırına", cerceveler[-1]["result"]["answer"])


class SohbetBaglantiTesti(unittest.TestCase):
    runtime = NS(runtime=NS(compiler=NS(memory=Memory())))

    def test_ajan_cevaplar_ve_hatirlanir(self):
        def sahte(*a, **k):
            yield {"type": "token", "delta": "tamam"}
            yield {"type": "done", "result": {"answer": "tamam", "intent": "AJAN"}}
        with patch.object(ajan, "ACIK", True), patch.object(ajan, "stream", sahte), \
             patch.object(chat, "_remember") as hatirla:
            cerceveler = list(chat.stream("bu ay kac siparis geldi", self.runtime, None))
        self.assertEqual(cerceveler[-1]["result"]["answer"], "tamam")
        hatirla.assert_called_once()

    def test_eylem_istegi_ajana_gitmez(self):
        with patch.object(ajan, "ACIK", True), patch.object(ajan, "stream") as ajan_akis, \
             patch.object(chat, "route", return_value={"answer": "x"}):
            list(chat.stream("vireon fiyatını 900e düşür", self.runtime, None))
        self.assertEqual(conversation.classify("vireon fiyatını 900e düşür").intent,
                         conversation.ACTION_REQUEST)
        ajan_akis.assert_not_called()

    def test_ajan_baslayamazsa_eski_yol(self):
        def bozuk(*a, **k):
            raise ajan.AjanKullanilamaz("SDK yok")
            yield  # uretec olsun diye; buraya hic gelinmez
        with patch.object(ajan, "ACIK", True), patch.object(ajan, "stream", bozuk), \
             patch.object(chat, "route", return_value={"answer": "eski yol"}) as eski:
            cerceveler = list(chat.stream("bu ay kac siparis geldi", self.runtime, None))
        eski.assert_called_once()
        self.assertEqual(cerceveler[-1]["result"]["answer"], "eski yol")


if __name__ == "__main__":
    unittest.main()
