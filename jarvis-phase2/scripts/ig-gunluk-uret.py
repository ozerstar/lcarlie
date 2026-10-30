#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GÜNLÜK INSTAGRAM PAKETİ: her gün BİR ürün için 5 içerik.

SAHİP (30.10.2026): "otomasyon gibi günlük kendi kendine çalışsın, sisteme
bağla. Başına uzman ver. Günlük bir ürün için kapsamlı 4-5 içerik çıkartsın."

GÜNÜN PAKETİ (5 içerik, aynı ürün):
  1 REELS  -- kanca formülü A, saniye saniye çekim planı
  2 REELS  -- FARKLI formül; iki video aynı kancayla açılırsa biri boşa gider
  3 KARUSEL -- 5-7 kare, her karenin metni ayrı
  4 STORY  -- 4-5 kare, en az birinde etkileşim (anket / soru kutusu)
  5 TEK_GORSEL -- akış gönderisi

ZİNCİR (en çok 4 model çağrısı)
  ürün seçimi (döngü, ölçülmüş satış eşitlikte önde)
  -> YAZAR 5 içeriği JSON yazar
  -> KOD ölçer: {S#} cümleleri havuzdan AYNEN, kanca puanı, caption biçimi,
     yapay zekâ kokusu, YASAK NESNE (semptom/fizyoloji/sonuç), mevzuat
  -> İNSTAGRAM İÇERİK DİREKTÖRÜ inceler, düzeltme verir
  -> kapıdan geçemeyen içerik YAZARA notlarla geri döner (tek tur)
  -> DİREKTÖR son kararı verir -> core.ig_gonderi_plani (ONERI) -> panel

🔴 ÜRÜN CÜMLESİ YAZILMAZ, AYIKLANIR. Yazar ürün etkisini kendi cümlesiyle
kuramaz; {S1}..{Sn} referansı verir, kod yayındaki Wix metninin mevzuattan
TEMİZ geçmiş cümlesini AYNEN koyar. Serbest metinde iddia fiili ya da
yasak nesne varsa içerik BULGULU olur ve şema onu onaylatmaz.

🔴 YAYIN YOK. Paket ONERI olarak yazılır; sahip panelde onaylar.
🔴 ÜRÜNLÜ AI GÖRSELİ YOK. Brief gerçek çekim ister (sahip kuralı).
🔴 AYNI GÜNE İKİNCİ PAKET YOK. (gun, sira) şemada tekil.

İLK KOŞUDAN DERS (30.10.2026, SERALIMBO): küçük model (haiku) ile yazılan
pakette havuz cümleleri yamalı oturdu ("kullanılır.. Diz"), beş caption'ın
beşinde ilk satır 125'i aştı ve "Sızlayan bacaklar", "rahat uyku", "Sonuç:
fark" mevzuat denetiminden geçti. Model Sonnet'e alındı, yasak nesne kapısı
ve revizyon turu eklendi.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import pathlib
import re
import sys
import time

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
# 🔴 ZAMAN AŞIMI: sağlayıcı varsayılanı 60 sn. Sonnet 5 içeriği bu sürede
# bitiremedi ve çağrılar sessizce gemini-flash-lite'a düştü (30.10.2026
# ölçüldü: 4 çağrının 3'ü yedekte). Müşteriye giden metin yedek modelde
# yazılmasın diye bu iş için 480 sn. providers modülü bunu import anında okur.
os.environ.setdefault("JARVIS_PROVIDER_TIMEOUT_S", "480")

from jarvis import compliance, ig_ustasi, providers  # noqa: E402

# Haftalık hattın ölçüm, CTA ve denetim işlevleri AYNEN kullanılır: aynı
# kararı iki yerde ayrı ayrı yazmak, birinin diğerinden sessizce ayrılması
# demek (bu projede hashtag tavanında yaşandı).
_sp = importlib.util.spec_from_file_location(
    "ig_gonderi_uret", str(KOK / "scripts" / "ig-gonderi-uret.py"))
haftalik = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(haftalik)
psql = haftalik.psql

KATALOG = pathlib.Path(os.environ.get(
    "JARVIS_STATE_DIR", str(KOK / "state"))) / "katalog.json"
IS_ANAHTARI = "ig_gunluk"
UZMAN = "ig_icerik_direktoru"
BICIM_SIRASI = ("REELS", "REELS", "KARUSEL", "STORY", "TEK_GORSEL")
KANCA_ESIGI = 55   # altı revizyona gider; puan eleme içindir, tahmin değil
# Yazı kalitesi müşteriye gidiyor: varsayılan Claude modeli (haiku) ilk
# koşuda yetersiz Türkçe üretti. Değiştirmek için ortam değişkeni yeter.
MODEL = os.environ.get("IG_GUNLUK_MODEL", "claude-sonnet-5-5")
# Günlük pakette kullanılmayan formüller: ürün bazında GERÇEK müşteri
# sorusu/itirazı verisi yok; model "her hafta soruyorsunuz" diye uydurdu.
GUNLUK_DISI_FORMUL = {"DOGRUDAN_SORU", "ITIRAZ"}


# --------------------------------------------------------------------------
# ÜRÜN SEÇİMİ
# --------------------------------------------------------------------------
def uygun_urunler(katalog: dict) -> list:
    """Paket yazılabilecek ürünler: yayında, görseli var, en az 3 temiz cümle.

    Cümlesi az ürüne 5 içerik yazdırmak, aynı iki cümleyi beş kez
    tekrarlatmak demek -- o ürün önce katalog metninde zenginleşmeli.
    """
    return [u for u in katalog.get("urunler") or []
            if str(u.get("yayinda")).lower() in ("true", "1")
            and u.get("gorseller") and len(u.get("satis_cumleleri") or []) >= 3]


def gunun_urunu(katalog: dict, olcum: dict, zorla: str = "") -> tuple:
    """(ürün, amaç, dayanak). Döngü: en uzun süredir paket almayan önce.

    Satışı ölçülmüş ürün eşitlikte öne geçer ama döngüyü TEKELE ALMAZ: her
    gün VIREON yazmak, portföyün geri kalanını hiç denememek olurdu.
    """
    adaylar = uygun_urunler(katalog)
    if zorla:
        adaylar = [u for u in adaylar if u["slug"] == zorla]
        if not adaylar:
            raise SystemExit("DURDU: '%s' uygun ürünler arasında yok" % zorla)
    if not adaylar:
        raise SystemExit("DURDU: paket yazılabilecek ürün yok (katalog.json)")

    son = {r["urun_slug"]: r["son"] for r in psql(
        "SELECT row_to_json(t) FROM (SELECT urun_slug, max(gun)::text AS son"
        " FROM core.ig_gonderi_plani WHERE kaynak = 'GUNLUK'"
        " GROUP BY 1) t;")}
    satan = {s["urun_adi"]: s for s in olcum["satan"]}

    def anahtar(u):
        return (son.get(u["slug"]) or "0000-00-00",
                0 if u["ad"] in satan else 1,
                -float(u.get("fiyat") or 0))

    u = sorted(adaylar, key=anahtar)[0]
    s = satan.get(u["ad"])
    gecmis = son.get(u["slug"])
    sira = ("ilk kez" if not gecmis else "son günlük paketi %s" % gecmis)
    if s:
        return u, "SATIS", ("ÖLÇÜLDÜ: %d adet / %d sipariş / %s TL net ciro "
                            "(mart.urun_sinyal). Döngü: %s."
                            % (s["adet"], s["siparis"], s["ciro"], sira))
    return u, "TANITIM", ("Satışı ÖLÇÜLMEDİ. Günlük döngüde sırası geldi "
                          "(%s); %d temiz katalog cümlesi var. Sonuç okunana "
                          "kadar DENEME." % (sira, len(u["satis_cumleleri"])))


# --------------------------------------------------------------------------
# MODEL ÇAĞRILARI
# --------------------------------------------------------------------------
def _json_ayikla(metin: str):
    """Model cevabından ilk JSON nesnesini çıkarır."""
    m = re.search(r"```(?:json)?\s*(.+?)```", metin or "", re.S)
    govde = m.group(1) if m else metin
    bas = min([i for i in (govde.find("{"), govde.find("[")) if i >= 0] or [0])
    return json.loads(govde[bas:])


CAGRILAR: list[str] = []


def _cagir(sistem: str, istek: str, azami: int):
    """Bütçe yüksek tutulur: Sonnet 5.5 kendiliğinden 'düşünme' bloğu açıyor
    ve bütçe dar kalırsa metin BOŞ dönüyor (30.10.2026 ölçüldü: 4 çağrının
    2'si "claude=bos cevap" ile gpt-5-mini'ye düştü). Yedeğe düşerse Claude
    bir kez daha denenir; yine düşerse yedek cevap kullanılır ve `modeller`
    alanında görünür."""
    cfg = dict(providers.load_env())
    cfg["CLAUDE_MODEL"] = MODEL
    mesaj = [{"role": "system", "content": sistem}, {"role": "user", "content": istek}]
    r = providers.generate(mesaj, max_tokens=azami, env=cfg, is_anahtari=IS_ANAHTARI)
    if r.get("provider") != "claude":
        print("  ! claude düştü (%s), bir kez daha deneniyor" % "; ".join(
            "%s=%s" % (x["provider"], x["result"][:40]) for x in r.get("attempts") or []))
        r = providers.generate(mesaj, max_tokens=azami, env=cfg, is_anahtari=IS_ANAHTARI)
    if r.get("truncated"):
        raise RuntimeError("model cevabı kesildi (%s)" % r.get("model"))
    CAGRILAR.append("%s/%s" % (r["provider"], r["model"]))
    if r.get("attempts"):
        # Yedeğe düşüş görünür olsun: hangi sağlayıcı neden düştü.
        print("  ! yedek model: %s (%s)" % (
            r["model"], "; ".join("%s=%s" % (x["provider"], x["result"][:60])
                                  for x in r["attempts"])))
    return _json_ayikla(r["text"])


def _formul_metni() -> str:
    return "\n".join(
        "- %s (%s): %s | örnek: %s | ekran: %s | TUZAK: %s"
        % (k, f["ad"], f["sablon"], f["ornek"], f["ekran"], f["tuzak"])
        for k, f in ig_ustasi.FORMULLER.items() if k not in GUNLUK_DISI_FORMUL)


MEVZUAT_BLOGU = """MEVZUAT (L'CARLIÉ kozmetik; denetlenen fiil değil NESNE):
- Serbest metinde izinli nesneler YALNIZ: görünüm, his, doku, nem hissi,
  konfor, koku, kullanım anı/ritüeli.
- YASAK: semptom (sızlama, ağrı, şişlik, kramp, uyuşma, kaşıntı, kızarıklık,
  yara, çatlak, akne, varis, selülit), fizyolojik işlev (dolaşım, kan,
  damar, emilim, hücre, kolajen, elastikiyet, hormon, uyku, "uyurken",
  dinlenme, onarım, yenilenme, detoks), sonuç vaadi ("fark gör", "sonuç:",
  önce/sonra, yüzde, "X günde", kanıtlanmış, garanti), "en iyi / tek /
  klinik", "içermez" kalıbı, başka markayı kötüleme, hastalık adıyla kitle.
- Ürünün ne yaptığı YALNIZ {S#} cümleleriyle söylenir."""

YAZAR_SISTEM = """Sen L'CARLIÉ'nin kıdemli Instagram içerik yazarısın. Türk kozmetik
markası; dil Türkçe, akıcı, doğal, sade, abartısız. Konuşma dili gibi ama
kusursuz dilbilgisiyle. Bugün TEK bir ürün için 5 içerik yazacaksın. Yayın
yapmazsın; her şey insan onayına gider.

CÜMLE HAVUZU KURALI (en önemli kural)
- Ürünün etkisi hakkında KENDİ cümleni kurma. Havuzdaki cümlelere {S1},
  {S2} diye referans ver; kod cümleyi AYNEN yerleştirir.
- {S#} TEK BAŞINA, TAM BİR CÜMLEDİR: kendi satırında ya da iki cümle
  arasında durur. Önüne/arkasına kelime ekleme, cümle ortasına koyma,
  arkasına nokta koyma (cümle zaten noktayla biter). YANLIŞ: "{S1} ile
  masaj." DOĞRU: "{S1}\\nAkşam, diz ve baldıra masajla uygula."
- Serbest metinde etki fiili KULLANMA: kazandırır, sağlar, korur, besler,
  nemlendirir, azaltır, yatıştırır, rahatlatır, onarır, destekler, önler.

{mevzuat}

CAPTION BİÇİMİ
- 1. satır: yalnız kanca, en çok 110 karakter. Sonra boş satır.
- Gövde 2-5 kısa satır ({S#} satırları dahil), son satır net çağrı.
- Link yazma; "profildeki bağlantı" de. En çok 3 emoji. Uzun tire (—)
  kullanma. Hashtag'ler caption'da değil "hashtagler" alanında (en çok 5).
- Yapay zekâ kokan kalıp yasak: hazır mısınız, eşsiz, vazgeçilmez, büyülü,
  sırrı, adeta, kendinizi şımartın, unutmayın, hadi gelin, yolculuk,
  deneyimleyin, fark yaratır.

KANCA
- Söylenen kanca 4-10 kelime; ilk 3 kelimede merak/gerilim; selam, önsöz,
  ürün adıyla açılış YOK. Ekran kancası en çok 6 kelime, söylenen
  kancanın daha kısa ve sert hâli. İki REELS FARKLI formül kullanır.
- Söz verilen şey videonun yarısından önce gelir.
- 5 içeriğin 5'i de FARKLI formül kullanır; aynı kanca cümlesi iki kez geçmez.

KANCA FORMÜLLERİ (yalnız bunlar):
{formuller}

GÖRSEL BRIEF: GERÇEK ÇEKİM. Ürün ambalajı yapay zekâya çizdirilmez.
Bütçesiz, telefonla çeken küçük ekip için uygulanabilir yaz.

ÇIKTI: yalnız JSON, açıklama yok:
{{"icerikler": [  // tam 5 öğe, bu sırayla: REELS, REELS, KARUSEL, STORY, TEK_GORSEL
  {{"bicim": "REELS",
    "formul": "FORMUL_KODU",
    "kanca": "söylenen kanca",
    "ekran_kancasi": "<= 6 kelime",
    "senaryo": [{{"sn": "0-2", "goruntu": "kamera ne görüyor", "ses": "ne söyleniyor", "ekran": "ekran yazısı"}}],
    "kareler": [],
    "caption": "kanca\\n\\ngövde satırları\\nçağrı",
    "hashtagler": ["#..."],
    "gorsel_brief": "çekim talimatı"}}
]}}
REELS: "senaryo" 15-30 sn, 5-7 satır, son satır çağrı; "kareler": [].
KARUSEL: "senaryo": [], "kareler" 5-7 öğe {{"no","baslik","metin","etkilesim"}}, 1. kare kanca.
STORY: "senaryo": [], "kareler" 4-5 öğe, en az birinde etkilesim "anket: ..." ya da "soru kutusu: ...".
TEK_GORSEL: "senaryo": [], "kareler" 1 öğe (görseldeki yazı)."""

UZMAN_SISTEM = """Sen L'CARLIÉ'nin Instagram İçerik Direktörüsün: 12 yıllık sosyal
medya ve kozmetik iletişimi deneyimi. Yazarın içeriklerini yayına
hazırlık açısından inceliyorsun. Nazik değil, net ve somut ol.

Ölçütlerin: ilk 2 saniye kaydırmayı durdurur mu; söz verilen şey erken
geliyor mu; iki reels birbirini tekrar ediyor mu; ürüne özgü mü (rakip de
aynısını söyleyebilir mi); Türkçe doğal ve kusursuz mu; mevzuat; yapay
zekâ kokusu; telefonla küçük ekip çekebilir mi.

{mevzuat}

Kod ölçümleri sana veriliyor (kanca puanı, biçim notları, yasak nesne,
mevzuat). Kod BULGU verdiyse o içerik GECER olamaz. Puan yalnız eleme
içindir; kararını içeriğe dayandır.

Düzeltme yazarsan: ürün etkisi yalnız {S#} referansıyla, {S#} kendi
satırında tam cümle olarak; serbest metinde etki fiili yok. Caption'ın
1. satırı yalnız kanca (<= 110 karakter), sonra boş satır.

ÇIKTI: yalnız JSON:
{{"degerlendirme": [   // her içerik için bir öğe, verilen "sira" ile
  {{"sira": 1,
   "karar": "GECER" | "DUZELT",
   "not": "1-2 cümle: neden; DUZELT ise neyin değişmesi gerektiği",
   "itiraz": "bu içeriğe karşı en güçlü kreatif ya da ticari argüman",
   "yanit": "itiraza cevabın; haklıysa ne değişti",
   "yeni_kanca": "", "yeni_ekran_kancasi": "", "yeni_caption": ""}}
],
 "gunun_notu": "paketin bütünü için 2 cümle: en güçlü içerik ve çekim sırası"}}"""

REVIZYON_SISTEM = """Sen L'CARLIÉ'nin kıdemli Instagram içerik yazarısın. Aşağıdaki
içerikler kalite kapısından GEÇEMEDİ. Her birini direktörün notu ve kod
bulgularına göre YENİDEN yaz. Aynı JSON şemasıyla, yalnız verilen
içerikleri, "sira" alanını koruyarak döndür:
{{"icerikler": [{{"sira": 1, "bicim": "...", "formul": "...", "kanca": "...",
  "ekran_kancasi": "...", "senaryo": [...], "kareler": [...], "caption": "...",
  "hashtagler": [...], "gorsel_brief": "..."}}]}}

{kurallar}"""


# --------------------------------------------------------------------------
# GENİŞLETME + ÖLÇÜM
# --------------------------------------------------------------------------
def havuz_temizle(cumle: str) -> str:
    """Katalog ayrıştırıcısının başlık dikişi: "Misk adaçayı Misk adaçayı
    yağı, ..." -- bölüm başlığı cümlenin önüne yapışmış. Tekrar eden baş
    (1-4 kelime) bir kez bırakılır. Cümlenin kendisi DEĞİŞMEZ."""
    c = (cumle or "").strip()
    m = re.match(r"^((?:\S+\s+){0,3}\S+)\s+\1(?=\s|,|$)", c)
    return c[len(m.group(1)):].lstrip() if m else c


def genislet(metin: str, havuz: list) -> tuple:
    """{S#} -> havuzdaki cümle AYNEN. Olmayan referans hata notudur."""
    eksik = []

    def degis(m):
        i = int(m.group(1)) - 1
        if 0 <= i < len(havuz):
            return havuz[i]
        eksik.append(m.group(0))
        return ""
    return re.sub(r"\{S(\d+)\}", degis, metin or ""), eksik


def _temizle(metin: str, havuz: list) -> str:
    """Yayına giden biçim: referans aç, tipografi + dikiş izlerini düzelt."""
    acik, _ = genislet(metin, havuz)
    return ig_ustasi.noktalama_duzelt(ig_ustasi.insanlastir(acik))


def _metin_alanlari(ic: dict) -> str:
    """Denetime giren TÜM serbest metin (referanslar açılmadan)."""
    parca = [ic.get("kanca", ""), ic.get("ekran_kancasi", ""), ic.get("caption", "")]
    for s in ic.get("senaryo") or []:
        parca += [s.get("ses", ""), s.get("ekran", ""), s.get("goruntu", "")]
    for k in ic.get("kareler") or []:
        parca += [k.get("baslik", ""), k.get("metin", ""), k.get("etkilesim", "")]
    return "\n".join(str(p) for p in parca if p)


def olc(ic: dict, havuz: list, urun: dict) -> dict:
    """Bir içeriğin kod ölçümleri. Model değil, kural."""
    ham = _metin_alanlari(ic)
    serbest = ig_ustasi.serbest_iddia(ham)
    nesne = ig_ustasi.yasak_nesne(ham, tuple(urun.get("zorunlu_uyarilar") or ()))
    genis, eksik = genislet(ham, havuz)
    caption = _temizle(ic.get("caption", ""), havuz)
    etiketler = [e if str(e).startswith("#") else "#" + str(e)
                 for e in (ic.get("hashtagler") or []) if str(e).strip()]
    etiketler = list(dict.fromkeys(etiketler))[:compliance.HASHTAG_CAP]
    bicim_notu = ig_ustasi.caption_denetle(caption, etiketler, compliance.HASHTAG_CAP)
    if len((ic.get("ekran_kancasi") or "").split()) > 6:
        bicim_notu.append("Ekran kancası 6 kelimeyi geçiyor.")
    koku = ig_ustasi.koku_bul(genis)
    if koku:
        bicim_notu.append("Senaryo/karede yapay zekâ kokusu: " + ", ".join(koku[:4]))
    if (ic.get("formul") or "") in GUNLUK_DISI_FORMUL:
        bicim_notu.append("Günlük pakette kullanılmayan formül: %s" % ic.get("formul"))
    puan = ig_ustasi.kanca_puani(ic.get("kanca", ""), urun.get("ad", ""))
    denetim, notu = haftalik.denetle(genis + "\n" + caption, etiketler)
    sorun = []
    if serbest:
        sorun.append("Serbest metinde iddia fiili (havuz dışı): " + ", ".join(serbest[:5]))
    if nesne:
        sorun.append("Yasak nesne: " + ", ".join(nesne[:6]))
    if eksik:
        sorun.append("Havuzda olmayan cümle referansı: " + ", ".join(eksik))
    if sorun:
        denetim = "BULGULU"
        notu = " · ".join(filter(None, [notu] + sorun))[:900]
    return {"caption": caption, "etiketler": etiketler, "bicim_notu": bicim_notu,
            "puan": puan, "denetim": denetim, "denetim_notu": notu}


def tekrar_isaretle(icerikler: list, olcumler: list) -> None:
    """Aynı formülü ikinci kez kullanan içerik biçim notu alır (revizyona gider).

    İlk kuru koşuda karusel reels-1'in, tek görsel reels-2'nin formülünü
    tekrarladı; aynı gün aynı kancayla açılan iki gönderi birbirini yer.
    """
    gorulen = {}
    for i, ic in enumerate(icerikler, 1):
        f = (ic.get("formul") or "").strip()
        notlar = [n for n in olcumler[i - 1]["bicim_notu"] if not n.startswith("Formül tekrarı")]
        if f and f in gorulen:
            notlar.append("Formül tekrarı: %s, %d. içerikte de var." % (f, gorulen[f]))
        else:
            gorulen.setdefault(f, i)
        olcumler[i - 1]["bicim_notu"] = notlar


def kapidan_gecer(o: dict) -> bool:
    return (o["denetim"] == "TEMIZ" and o["puan"]["puan"] >= KANCA_ESIGI
            and not o["bicim_notu"])


def yazar_istegi(u: dict, amac: str, havuz: list) -> str:
    cumleler = "\n".join("{S%d} %s" % (i + 1, c) for i, c in enumerate(havuz))
    uyarilar = "\n".join("- " + x for x in (u.get("zorunlu_uyarilar") or [])[:6])
    return ("ÜRÜN: %s\nFİYAT: %s TL\nAMAÇ: %s\nÖZET: %s\nKULLANIM: %s\n\n"
            "CÜMLE HAVUZU (ürün etkisi yalnız bunlardan, referansla):\n%s\n\n"
            "ZORUNLU UYARILAR (aynen yazılabilir; iddia gibi kullanılmaz):\n%s\n\n"
            "Ölçülen: video ortalama 51,5 beğeni, karusel 15,9, tek görsel 14,7 "
            "(raw.ig_medya). İzleyicinin çoğu sessiz izler: ekranda altyazı şart."
            % (u["ad"], int(float(u.get("fiyat") or 0)), amac, u.get("ozet") or "",
               u.get("kullanim") or "", cumleler, uyarilar or "-"))


def _icerik_ozeti(i: int, ic: dict, o: dict, havuz: list) -> dict:
    return {"sira": i, "bicim": ic.get("bicim"), "formul": ic.get("formul"),
            "kanca": ic.get("kanca"), "ekran_kancasi": ic.get("ekran_kancasi"),
            "senaryo": ic.get("senaryo"), "kareler": ic.get("kareler"),
            "caption_referansli": ic.get("caption"),
            "caption_yayindaki": o["caption"],
            "kod_olcumu": {"kanca_puani": o["puan"]["puan"],
                           "kanca_kusurlari": o["puan"]["kusurlar"],
                           "bicim_notlari": o["bicim_notu"],
                           "mevzuat": o["denetim"], "mevzuat_notu": o["denetim_notu"]}}


def uzman_incele(icerikler: list, olcumler: list, havuz: list, siralar=None) -> dict:
    siralar = siralar or range(1, len(icerikler) + 1)
    satirlar = [json.dumps(_icerik_ozeti(i, icerikler[i - 1], olcumler[i - 1], havuz),
                           ensure_ascii=False) for i in siralar]
    havuz_metni = "\n".join("{S%d} %s" % (i + 1, c) for i, c in enumerate(havuz))
    veri = _cagir(UZMAN_SISTEM.replace("{mevzuat}", MEVZUAT_BLOGU)
                  .replace("{{", "{").replace("}}", "}"),
                  "CÜMLE HAVUZU:\n%s\n\nİÇERİKLER:\n%s" % (havuz_metni, "\n".join(satirlar)),
                  16000)
    return veri


def uzman_duzeltmesi_uygula(ic: dict, d: dict) -> bool:
    degisti = False
    if d.get("karar") == "DUZELT":
        for alan, yeni in (("kanca", "yeni_kanca"), ("ekran_kancasi", "yeni_ekran_kancasi"),
                           ("caption", "yeni_caption")):
            if (d.get(yeni) or "").strip():
                ic[alan] = d[yeni].strip()
                degisti = True
    return degisti


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urun", default="", help="slug: döngü yerine bu ürün")
    ap.add_argument("--gun", default="", help="YYYY-MM-DD (varsayılan bugün)")
    ap.add_argument("--kuru", action="store_true", help="yazmadan göster")
    a = ap.parse_args()
    t0 = time.time()
    gun = a.gun or dt.date.today().isoformat()

    if not a.kuru and psql(
            "SELECT row_to_json(t) FROM (SELECT count(*) n FROM"
            " core.ig_gonderi_plani WHERE kaynak = 'GUNLUK' AND gun = :'gun') t;",
            {"gun": gun})[0]["n"]:
        print("bugünün paketi zaten var (%s) -- ikinci paket yazılmaz" % gun)
        return 0
    if not KATALOG.exists():
        print("DURDU: katalog yok -- önce scripts/katalog-uret.py")
        return 1
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    olcum = haftalik.olcumler()
    u, amac, dayanak = gunun_urunu(katalog, olcum, a.urun)
    havuz = [havuz_temizle(c) for c in u["satis_cumleleri"] if len(c) < 240]
    print("GÜNÜN ÜRÜNÜ  %s  · %s\n  %s" % (u["ad"], amac, dayanak))

    # 1) YAZAR
    sistem = (YAZAR_SISTEM.replace("{formuller}", _formul_metni())
              .replace("{mevzuat}", MEVZUAT_BLOGU)
              .replace("{{", "{").replace("}}", "}"))
    veri = _cagir(sistem, yazar_istegi(u, amac, havuz), 28000)
    icerikler = list(veri.get("icerikler") or [])
    if [i.get("bicim") for i in icerikler] != list(BICIM_SIRASI):
        raise SystemExit("DURDU: yazar 5 içeriği beklenen sırada vermedi: %s"
                         % [i.get("bicim") for i in icerikler])
    olcumler = [olc(ic, havuz, u) for ic in icerikler]
    tekrar_isaretle(icerikler, olcumler)

    # 2) DİREKTÖR -- ilk inceleme ve doğrudan düzeltmeler
    ilk = uzman_incele(icerikler, olcumler, havuz)
    ilk_karar = {int(d.get("sira", 0)): d for d in ilk.get("degerlendirme") or []}
    for i, ic in enumerate(icerikler, 1):
        if uzman_duzeltmesi_uygula(ic, ilk_karar.get(i) or {}):
            olcumler[i - 1] = olc(ic, havuz, u)
    tekrar_isaretle(icerikler, olcumler)

    # 3) KAPIDAN GEÇEMEYEN -> YAZARA GERİ (tek tur)
    kalan = [i for i, o in enumerate(olcumler, 1)
             if not kapidan_gecer(o) or (ilk_karar.get(i) or {}).get("karar") == "DUZELT"]
    revize = set()
    if kalan:
        notlar = []
        for i in kalan:
            ozet = _icerik_ozeti(i, icerikler[i - 1], olcumler[i - 1], havuz)
            ozet["direktor_notu"] = (ilk_karar.get(i) or {}).get("not", "")
            notlar.append(json.dumps(ozet, ensure_ascii=False))
        kurallar = (YAZAR_SISTEM.replace("{formuller}", _formul_metni())
                    .replace("{mevzuat}", MEVZUAT_BLOGU)
                    .split("ÇIKTI:")[0])
        rev = _cagir(REVIZYON_SISTEM.replace("{kurallar}", kurallar)
                     .replace("{{", "{").replace("}}", "}"),
                     "ÜRÜN: %s\nCÜMLE HAVUZU:\n%s\n\nGEÇEMEYEN İÇERİKLER:\n%s" % (
                         u["ad"], "\n".join("{S%d} %s" % (k + 1, c) for k, c in enumerate(havuz)),
                         "\n".join(notlar)), 24000)
        for yeni in rev.get("icerikler") or []:
            i = int(yeni.get("sira") or 0)
            if i in kalan and yeni.get("bicim") == BICIM_SIRASI[i - 1]:
                icerikler[i - 1] = yeni
                olcumler[i - 1] = olc(yeni, havuz, u)
                revize.add(i)
        tekrar_isaretle(icerikler, olcumler)

    # 4) DİREKTÖR -- son karar (revizyon olduysa bütün paket yeniden)
    son = uzman_incele(icerikler, olcumler, havuz) if revize else ilk
    kararlar = {int(d.get("sira", 0)): d for d in son.get("degerlendirme") or []}
    gunun_notu = (son.get("gunun_notu") or "").strip()
    for i, ic in enumerate(icerikler, 1):
        # Son turdaki düzeltme de aynı kapıdan geçer, ayrıcalığı yok.
        if uzman_duzeltmesi_uygula(ic, kararlar.get(i) or {}):
            olcumler[i - 1] = olc(ic, havuz, u)
    tekrar_isaretle(icerikler, olcumler)

    cta, cta_gerekce = haftalik.cta_secimi(amac, olcum)
    modeller = " · ".join(dict.fromkeys(CAGRILAR))
    yazilan = 0
    for i, (ic, o) in enumerate(zip(icerikler, olcumler, strict=True), 1):
        d = kararlar.get(i) or {}
        notlar = list(o["bicim_notu"])
        if o["puan"]["puan"] < KANCA_ESIGI:
            notlar.append("Kanca puanı %d (< %d): %s" % (
                o["puan"]["puan"], KANCA_ESIGI,
                "; ".join(o["puan"]["kusurlar"]) or "somutluk/gerilim zayıf"))
        # Kod kapısı direktörden üstündür: kapıdan geçemeyen GECER olamaz.
        ukarar = d.get("karar") or "INCELENMEDI"
        if ukarar == "GECER" and not kapidan_gecer(o):
            ukarar = "DUZELT"
        uzman_notu = (d.get("not") or "").strip()
        if i in revize:
            uzman_notu = "[revize edildi] " + uzman_notu
        if i == 1 and gunun_notu:
            uzman_notu = (uzman_notu + "\nGÜNÜN NOTU: " + gunun_notu).strip()
        senaryo = [{k: _temizle(str(v), havuz) for k, v in s.items()}
                   for s in (ic.get("senaryo") or [])]
        kareler = [{k: (_temizle(str(v), havuz) if k != "no" else v) for k, v in kk.items()}
                   for kk in (ic.get("kareler") or [])]
        satir = {
            "urun_slug": u["slug"], "amac": amac, "bicim": ic["bicim"],
            "kanca": _temizle(ic.get("kanca") or "", havuz),
            "caption": o["caption"], "etiket": " ".join(o["etiketler"]),
            "brief": _temizle(ic.get("gorsel_brief") or "", havuz)
                     or haftalik.BRIEF.get(ic["bicim"], "Gerçek çekim."),
            "cta": cta, "ctag": cta_gerekce, "dayanak": dayanak,
            "itiraz": (d.get("itiraz") or "").strip(),
            "yanit": (d.get("yanit") or "").strip(),
            "denetim": o["denetim"], "notu": o["denetim_notu"] or "",
            "gun": gun, "sira": i,
            "ekran": _temizle(ic.get("ekran_kancasi") or "", havuz),
            "formul": (ic.get("formul") or "").strip(),
            "puan": o["puan"]["puan"],
            "senaryo": json.dumps({"senaryo": senaryo, "kareler": kareler},
                                  ensure_ascii=False),
            "uzman": UZMAN, "ukarar": ukarar,
            "unot": uzman_notu, "lint": " · ".join(notlar),
            "modeller": modeller,
        }
        print("  %d %-10s puan %3d  %-8s direktör %-8s%s %s" % (
            i, ic["bicim"], satir["puan"], satir["denetim"], ukarar,
            " (revize)" if i in revize else "", satir["kanca"][:60]))
        if a.kuru:
            continue
        psql("""INSERT INTO core.ig_gonderi_plani
          (urun_slug, amac, bicim, kanca, caption, hashtagler, gorsel_brief,
           cta, cta_gerekce, dayanak, itiraz, itiraza_yanit, denetim,
           denetim_notu, kaynak, gun, sira, ekran_kancasi, kanca_formulu,
           kanca_puani, senaryo, uzman, uzman_karari, uzman_notu, bicim_notu,
           modeller)
          VALUES (:'urun_slug', :'amac', :'bicim', :'kanca', :'caption',
                  string_to_array(NULLIF(:'etiket', ''), ' '), :'brief', :'cta',
                  :'ctag', :'dayanak', NULLIF(:'itiraz', ''), NULLIF(:'yanit', ''),
                  :'denetim', NULLIF(:'notu', ''), 'GUNLUK', :'gun'::date,
                  :'sira'::smallint, NULLIF(:'ekran', ''), NULLIF(:'formul', ''),
                  :'puan'::smallint, :'senaryo'::jsonb, :'uzman', :'ukarar',
                  NULLIF(:'unot', ''), NULLIF(:'lint', ''), :'modeller');""", satir)
        yazilan += 1

    print("\n%d içerik yazıldı · %d revize · %d model çağrısı (%s) · %.1f sn"
          % (yazilan, len(revize), len(CAGRILAR), modeller, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
