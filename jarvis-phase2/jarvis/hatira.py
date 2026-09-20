"""Hatıra: notları kelimeyle değil ANLAMLA bulmak.

NEDEN VAR
conversation_memory notları saklıyor ama arayamıyor. Not "VIREON birim fiyat
1,7x" diye yazıldıysa ve soru "geçen gün pahalı dediğin ürün hangisiydi" ise,
tam-kelime eşleşmesi boş döner. Bu projede o tuzağa on birden fazla kez
çarptık; Türkçede çekim ekleri yüzünden sabit dizgi karşılaştırması SESSİZCE
başarısız olur. Anlamsal arama o tuzağın dışındadır: ek de alsa, eş anlamlı da
olsa vektör yakın kalır.

KAYIT KAYNAĞI BURASI DEĞİL
Notun aslı conversation_memory'nin JSON dosyasında durur. Burası yalnızca o
dosyanın üstünde bir ARAMA DİZİNİdir. Bu bilinçli: mem0 çökse, postgres'e
erişilemese, Gemini kotayı doldursa bile TEK BİR NOT KAYBOLMAZ -- yalnızca
arama körelir, hatırlama durur değil. Dizin her zaman yeniden kurulabilir;
kaynak yeniden kurulamaz.

DIŞARI NE GİDİYOR -- SAHİP KARARI (20.09.2026)
Sahip kararı: şirket kanıtı dış sağlayıcıya gitmez, sohbet yerel kalır.
Bu modül o kararın içinde durur ve sınırı KOD ZORLAR, dikkat değil:

  * Ham sohbet dökümü kabul eden bir yol YOKTUR. kaydet() tek bir not cümlesi
    alır -- operatörün "bunu hatırla" dediği cümle. Transkript, müşteri
    mesajı, sipariş ya da ciro verisi buraya giremez çünkü girecek kapı yok.
  * infer=False sabittir. mem0 normalde metni bir LLM'e gönderip "bundan ne
    hatırlanmalı" diye sorar; o yol kapalı. Metni yalnız GÖMME çağrısı görür.
  * Telemetri kapalı doğrulanır. Açıksa modül çalışmayı REDDEDER -- kapatmayı
    unutmak sessiz bir sızıntı olurdu.

KANIT DEĞİLDİR
Buradaki satırlarda evidence_ref yok (karşılaştırın: ai_semantic.
memory_embedding'de NOT NULL). Burası TERCİH ve KARAR tutar
("yüzde bazlı toplu fiyat müdahalesi istiyorum"), şirket GERÇEĞİ tutmaz.
Şirket gerçeği mart görünümlerinden gelmeye devam eder. Bu yüzden veritabanı
tarafında mem0_writer core/mart/raw'ı okuyamaz: sınırı yetki tutuyor.

HER ŞEY YUMUŞAK BOZULUR
Postgres kapalı, ağ yok, anahtar yanlış -- hepsi BOŞ SONUÇ demektir, hata
değil. conversation_memory'nin kuralı burada da geçerli: bir konuşma,
transkripti okunamadı diye başarısız olmamalı.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import Any

# mem0 telemetri bayrağını İÇE AKTARILIRKEN okur -- bu satır importlardan
# önce gelmek zorunda, sonra gelirse hiçbir şey yapmaz.
os.environ.setdefault("MEM0_TELEMETRY", "false")

log = logging.getLogger(__name__)

KONTEYNER = "lcarlie-postgres"
KOLEKSIYON = "hatira"
BOYUT = 1024          # ai_semantic.memory_embedding ile aynı; bkz. migration 019
GEMINI_GOMME = "models/gemini-embedding-001"
GEMINI_LLM = "gemini-3.5-flash-lite"   # bu sunucuda ölçülmüş çalışan ad
ARAMA_SINIRI = 5
MAX_NOT_KARAKTER = 600

# Benzerlik eşiği -- ÖLÇÜLDÜ, uydurulmadı (20.09.2026, 5 not / 6 soru):
#     doğru cevapların skoru        0.6591 - 0.7578
#     konuyla ilgili yan notlar     0.5905 - 0.6910
#     hiç ilgisi olmayan soru       0.4935 - 0.5355   ("kargo hangi gün teslim")
# 0.60, doğruların en düşüğünün (0.6591) altında ve ilgisizlerin en
# yükseğinin (0.5355) üstünde duruyor.
#
# BU SAYI GEÇİCİDİR. Beş notla ölçüldü; not sayısı arttıkça dağılım
# değişir ve YENİDEN ÖLÇÜLMELİDİR. Ölçmeden değiştirmeyin, ölçmeden
# güvenmeyin -- bu dosyadaki tek keyfi sayı olmasın diye buraya yazıldı.
BENZERLIK_ESIGI = 0.60

_kilit = threading.Lock()
_bellek: Any = None
_kurulum_hatasi: str | None = None


def _postgres_ip() -> str | None:
    """Konteynerin IP'si -- compose'da SABİT IP YOK.

    Bu yüzden adres çalışma anında çözülür, koda yazılmaz. Bedeli şu ve
    açıkça söylenmeli: postgres yeniden başlayıp BAŞKA bir IP alırsa, bu
    süreç bir sonraki bağlantı denemesine kadar hatırayı bulamaz --
    _sifirla() o denemede yeniden çözer.
    """
    try:
        out = subprocess.run(
            ["docker", "inspect", KONTEYNER, "--format",
             "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"],
            capture_output=True, text=True, timeout=10)
        parcalar = out.stdout.split()
        return parcalar[0] if parcalar else None
    except Exception:                                             # noqa: BLE001
        return None


def _telemetri_kapali() -> bool:
    """Bayrağı okumakla yetinme -- mem0'ın kendi değişkenine bak.

    os.environ doğru olsa bile mem0 daha önce başka bir değerle içe
    aktarılmış olabilir. Sızıntının sessiz olanı en kötüsüdür.
    """
    try:
        from mem0.memory import telemetry as t
        return getattr(t, "MEM0_TELEMETRY", True) is False
    except Exception:                                             # noqa: BLE001
        return False


def _yapilandirma() -> dict[str, Any] | None:
    ip = _postgres_ip()
    pw = os.environ.get("MEM0_PG_PASSWORD")
    key = os.environ.get("GEMINI_API_KEY")
    if not (ip and pw and key):
        return None
    return {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": ip, "port": 5432,
                "dbname": os.environ.get("MEM0_PG_DB", "n8n"),
                "user": os.environ.get("MEM0_PG_USER", "mem0_writer"),
                "password": pw,
                "collection_name": KOLEKSIYON,
                "embedding_model_dims": BOYUT,
                "hnsw": True,
            },
        },
        "embedder": {
            "provider": "gemini",
            "config": {"model": GEMINI_GOMME, "embedding_dims": BOYUT,
                       "api_key": key},
        },
        # infer=False olduğu için bu LLM hiç çağrılmaz; mem0 yine de bir
        # yapılandırma bekliyor. Varsayılanı bırakırsak OpenAI'ı kurmaya
        # çalışır ve anahtar yokluğundan patlar -- bu yüzden ölçülmüş
        # çalışan Gemini adı veriliyor.
        "llm": {
            "provider": "gemini",
            "config": {"model": GEMINI_LLM, "api_key": key},
        },
    }


def _bellegi_al():
    global _bellek, _kurulum_hatasi
    with _kilit:
        if _bellek is not None:
            return _bellek
        cfg = _yapilandirma()
        if cfg is None:
            _kurulum_hatasi = "yapilandirma eksik (IP / parola / GEMINI_API_KEY)"
            return None
        try:
            from mem0 import Memory
            if not _telemetri_kapali():
                _kurulum_hatasi = "mem0 telemetrisi ACIK -- calismayi reddediyorum"
                log.error(_kurulum_hatasi)
                return None
            _bellek = Memory.from_config(cfg)
            _kurulum_hatasi = None
            return _bellek
        except Exception as e:                                    # noqa: BLE001
            _kurulum_hatasi = f"{type(e).__name__}: {e}"
            log.warning("hatira kurulamadi: %s", _kurulum_hatasi)
            return None


def _sifirla() -> None:
    """Bağlantıyı unut ki bir sonraki çağrı IP'yi yeniden çözsün."""
    global _bellek
    with _kilit:
        _bellek = None


def _ayniyi_sil(m: Any, metin: str, thread: str) -> None:
    """Birebir ayni metni tasiyan eski satirlari dizinden cikar."""
    try:
        hepsi = m.get_all(filters={"user_id": thread}, limit=1000)
        satirlar = hepsi.get("results", []) if isinstance(hepsi, dict) else (hepsi or [])
        for r in satirlar:
            if isinstance(r, dict) and (r.get("memory") or "").strip() == metin:
                m.delete(r["id"])
    except Exception as e:                                        # noqa: BLE001
        log.debug("ayni not taranamadi: %s", e)


def kaydet(not_metni: str, thread: str = "operator") -> bool:
    """Operatörün yazdığı TEK bir notu dizine ekle.

    Bilerek yalnız düz metin alır: burada rol/mesaj listesi kabul edilseydi
    bir gün oraya transkript geçirilirdi. Kapı yoksa kaza da olmaz.
    """
    metin = (not_metni or "").strip()
    if not metin:
        return False
    if len(metin) > MAX_NOT_KARAKTER:
        metin = metin[:MAX_NOT_KARAKTER]

    m = _bellegi_al()
    if m is None:
        return False
    try:
        # Ayni cumle ikinci kez yazilmasin. remember() dosyada bunu zaten
        # yapiyor (ayni notu silip yeniden ekliyor); dizin de ayni davranmali,
        # yoksa top_k butcesini ayni cumlenin kopyalari yer. Olculdu: ucer
        # kopya birikmisti.
        _ayniyi_sil(m, metin, thread)
        m.add([{"role": "user", "content": metin}],
              user_id=thread, infer=False)
        return True
    except Exception as e:                                        # noqa: BLE001
        log.warning("hatira kaydedilemedi: %s", e)
        _sifirla()
        return False


def ara(soru: str, limit: int = ARAMA_SINIRI,
        thread: str = "operator") -> list[str]:
    """Soruya anlamca yakın notlar. Hata = boş liste, asla istisna."""
    s = (soru or "").strip()
    if not s:
        return []
    m = _bellegi_al()
    if m is None:
        return []
    try:
        # İki ölçülmüş tuzak, ikisi de mem0 2.1.0'da:
        #
        # 1) API asimetrik: add() user_id'yi doğrudan alır, search() ve
        #    get_all() reddedip filters ister. Bu GÜRÜLTÜLÜ bir hataydı
        #    (ValueError), yani fark edilebilirdi.
        #
        # 2) Sınırın adı 'limit' DEĞİL, 'top_k'. limit= yazınca **kwargs'a
        #    düşüp SESSİZCE yok sayılıyor: limit=2 istedik, 5 sonuç geldi.
        #    Bu projede tekrar eden hata sınıfı tam olarak bu -- sessizce
        #    yok sayılan parametre. Adı doğru yazmak tek çare.
        sonuc = m.search(query=s, filters={"user_id": thread},
                         top_k=limit, threshold=BENZERLIK_ESIGI)
    except Exception as e:                                        # noqa: BLE001
        log.warning("hatira aranamadi: %s", e)
        _sifirla()
        return []

    satirlar = sonuc.get("results", []) if isinstance(sonuc, dict) else (sonuc or [])
    cikti: list[str] = []
    for r in satirlar:
        t = (r.get("memory") or "").strip() if isinstance(r, dict) else ""
        if t and t not in cikti:
            cikti.append(t)
    return cikti


def unut(parca: str, thread: str = "operator") -> int:
    """İçinde bu parça geçen notları dizinden sil. Kaç tane gittiğini döner.

    Bu bir kolaylık değil, DOĞRULUK meselesi: operatör bir notu unutturduysa
    o not aramada çıkmaya devam etmemeli. Kaynak dosyadan silinip dizinde
    kalsaydı, Jarvis geri alınmış bir kararı hatırlamaya devam ederdi --
    sessizce yanlış cevap veren bir hafıza, hafızasızlıktan kötüdür.
    """
    p = (parca or "").strip().casefold()
    if not p:
        return 0
    m = _bellegi_al()
    if m is None:
        return 0
    try:
        hepsi = m.get_all(filters={"user_id": thread}, limit=1000)
        satirlar = hepsi.get("results", []) if isinstance(hepsi, dict) else (hepsi or [])
    except Exception as e:                                        # noqa: BLE001
        log.warning("hatira taranamadi: %s", e)
        _sifirla()
        return 0

    silinen = 0
    for r in satirlar:
        if not isinstance(r, dict):
            continue
        if p in (r.get("memory") or "").casefold():
            try:
                m.delete(r["id"])
                silinen += 1
            except Exception as e:                                # noqa: BLE001
                log.warning("hatira silinemedi: %s", e)
    return silinen


def durum() -> dict[str, Any]:
    """Panel ve testler için: çalışıyor mu, kaç not var, neden çalışmıyor."""
    m = _bellegi_al()
    d: dict[str, Any] = {
        "kurulu": m is not None,
        "telemetri_kapali": _telemetri_kapali(),
        "hata": _kurulum_hatasi,
        "not_sayisi": None,
    }
    if m is None:
        return d
    try:
        hepsi = m.get_all(filters={"user_id": "operator"}, limit=1000)
        satirlar = hepsi.get("results", []) if isinstance(hepsi, dict) else (hepsi or [])
        d["not_sayisi"] = len(satirlar)
    except Exception as e:                                        # noqa: BLE001
        d["hata"] = f"{type(e).__name__}: {e}"
        _sifirla()
    return d
