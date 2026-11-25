#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLOG HATTI — günlük otonom SEO blog yayını (Jarvis rutini, Claude'a bağlı değil).

Alt komutlar:
  yukle      hazır yazıları + yedek konuları kuyruğa alır (slug'a göre idempotent)
  calis      durum makinesi (06:30 + saatlik devam). Günlük tavan: BLOG_GUNLUK_TAVAN (3)
  konu-bul   haftalık: GSC'de gösterimi olup 10. sıradan geride kalan, kapsanmamış sorgular
  rapor      günlük push + e-posta özeti (21:30)
  yetki      Wix anahtarının blog/medya/yönlendirme izinlerini ölçer (yazma yok)

Bayraklar: --kuru (Wix yazması ve tarayıcı kuyruğu YOK, DB'ye yazmaz; her şeyi
hesaplar ve /opt/lcarlie/blog-hatti/kuru/<slug>/ altına döker), --slug X (yalnız o yazı).

Durum makinesi (core.blog_kuyruk.durum):
  BEKLIYOR -> (yazım [PLAN/GSC] + TR kapıları) -> YAZILDI
  YAZILDI  -> (4 dile çeviri + dil kapıları, sahne işi kuyruğa) -> GORSEL_BEKLIYOR
  GORSEL_BEKLIYOR -> (ChatGPT sahnesi geldi; kapak x5 + iç görsel dizildi) -> GORSEL_HAZIR
  GORSEL_HAZIR -> (Wix: medya, TR yazı, 4 bağlı çeviri, canlı denetim) -> YAYINLANDI
  herhangi bir kapı reddi -> INSANA (+ sahibe bildirim); dış servis hatası -> HATA (yeniden denenir)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import blog_hatti as bh  # noqa: E402

TAVAN = int(os.environ.get("BLOG_GUNLUK_TAVAN", "3"))
KAYNAK_DIR = bh.KOK / "kaynak"
DURUM_DIR = bh.KOK / "durum"
YEDEK_DIR = bh.KOK / "yedek"
KURU_DIR = bh.KOK / "kuru"
ISTEYEN = "blog-hatti"
TZ = dt.timezone(dt.timedelta(hours=3))
GORSEL_EN_COK = 3

# Sahip kararları (25.11.2026) — kuyruğa yüklerken uygulanır.
SAHIP_KURALI = {  # plan_no -> (durum, sebep)
    "07": ("INSANA", "Sahip 25.11: bu içerik blogda ayrı yayınlanmayacak, /hikayemiz "
                                   "sayfasında kullanılacak."),
}
KATEGORI_VARSAYILAN = {"08": bh.KATEGORI["urun-rehber"], "09": bh.KATEGORI["botanik"],
                       "10": bh.KATEGORI["bilincli-bakim"]}
YONLENDIR = {  # yeni yazı yayınlanınca eski adresten 301 (sahip 25.11 onayı)
    "seramid-hyaluronik-asit-niasinamid-nemlendirici": ["/post/seramid-niasinamid-birlikte-kullanilir-mi"],
}


def simdi() -> dt.datetime:
    return dt.datetime.now(TZ)


def bugun() -> str:
    return simdi().date().isoformat()


def log(*a):
    print("[%s]" % simdi().strftime("%H:%M:%S"), *a, flush=True)


# ===================================================================== YÜKLE
def oncelik_hesapla(d: dict) -> int:
    no = d["plan_no"]
    if no.startswith("E"):
        return 300 + int(no[1:])
    n = int(no) if no.isdigit() else 99
    if d["tur"] == "REFRESH" and n <= 12:
        return 100 + n          # RAPOR: en hızlı kazanç ilk 12'deki REFRESH'ler
    return 200 + n


def yedek_konular() -> list[dict]:
    """RAPOR §6 'Yedek konular' tablosu -> PLAN satırları."""
    rapor = KAYNAK_DIR / "RAPOR.md"
    if not rapor.is_file():
        return []
    t = rapor.read_text(encoding="utf-8")
    m = re.search(r"## 6\..*?\n(.*?)\n## 7\.", t, re.S)
    if not m:
        return []
    out = []
    for satir in m.group(1).splitlines():
        h = [x.strip() for x in satir.strip().strip("|").split("|")]
        if len(h) < 6 or h[0] in ("Konu", "") or set(h[0]) <= {"-"}:
            continue
        tur_ham = h[3]
        tur = "REFRESH" if tur_ham.upper().startswith("REFRESH") else "NEW"
        mevcut = tur_ham.split()[1] if tur == "REFRESH" and len(tur_ham.split()) > 1 else None
        out.append({"konu": h[0], "anahtar": h[1], "urun": h[4], "not": h[5], "tur": tur, "mevcut_slug": mevcut})
    return out


def yukle(a) -> dict:
    k = bh.Kuyruk(kuru=a.kuru)
    sonuc = {"EKLENDI": 0, "GUNCELLENDI": 0, "DEGISMEDI": 0, "KURU": 0, "hata": []}
    for yol in sorted((KAYNAK_DIR / "tr").glob("*.html")):
        try:
            d = bh.hazir_dosya_oku(yol)
        except Exception as e:  # noqa: BLE001
            sonuc["hata"].append("%s: %s" % (yol.name, e))
            continue
        slug = d["mevcut_slug"] if d["tur"] == "REFRESH" and d["mevcut_slug"] else d["slug"]
        satir = {"slug": slug, "kaynak": "HAZIR", "plan_no": d["plan_no"], "oncelik": oncelik_hesapla(d),
                 "konu": d["baslik"], "tur": d["tur"], "mevcut_slug": d["mevcut_slug"],
                 "kategori_id": d["kategori_id"], "durum": "BEKLIYOR", "kaynak_dosya": d["kaynak_dosya"],
                 "kaynak_sha": d["kaynak_sha"], "icerik": d, "bekleme_sebebi": None}
        if not satir["kategori_id"] and d["tur"] == "NEW":
            satir["kategori_id"] = KATEGORI_VARSAYILAN.get(d["plan_no"], bh.KATEGORI["bilincli-bakim"])
        if d["plan_no"] in SAHIP_KURALI:
            satir["durum"], satir["bekleme_sebebi"] = SAHIP_KURALI[d["plan_no"]]
        sonuc[k.ekle(satir)] += 1
    for i, y in enumerate(yedek_konular()):
        slug = y["mevcut_slug"] or bh.slugla(y["anahtar"])
        satir = {"slug": slug, "kaynak": "PLAN", "plan_no": "Y%02d" % (i + 31), "oncelik": 600 + i,
                 "konu": y["konu"], "tur": y["tur"], "mevcut_slug": y["mevcut_slug"], "kategori_id": None,
                 "durum": "BEKLIYOR", "kaynak_dosya": "RAPOR.md §6", "kaynak_sha": bh.hashlib.sha256(
                     json.dumps(y, ensure_ascii=False).encode()).hexdigest()[:16],
                 "icerik": {"plan": y}, "bekleme_sebebi": None}
        sonuc[k.ekle(satir)] += 1
    log("yükle:", json.dumps(sonuc, ensure_ascii=False))
    return sonuc


# ================================================================ KONU BUL
MARKA = re.compile(r"(?i)(carl|karla|carla|lemos|trendyol|hepsiburada|fiyat|satın|indirim|kupon)")
BILGI = re.compile(r"(?i)(nedir|nasıl|ne işe|ne demek|zararlı|fayda|kullanılır|mı\b|mi\b|mu\b|mü\b|hangi|neden|"
                   r"ne zaman|kaç|farkı|rutin)")


def konu_bul(a) -> dict:
    k = bh.Kuyruk(kuru=a.kuru)
    ham = k.sql("SELECT coalesce(json_agg(x),'[]') FROM (SELECT sorgu, sum(gosterim) g, sum(tiklama) t, "
                "round(sum(sira*gosterim)/nullif(sum(gosterim),0),1) s FROM raw.gsc_sorgu "
                "WHERE tarih > current_date - 35 AND ulke IN ('tur','TUR','TR','tr') GROUP BY sorgu "
                "HAVING sum(gosterim) >= %d ORDER BY 2 DESC LIMIT 400) x;" % int(os.environ.get("BLOG_KONU_MIN_GOSTERIM", "5")))
    adaylar = json.loads(ham or "[]")
    mevcut = k.satirlar()
    kapsam = []
    for r in mevcut:  # her yazı: slug+konu+anahtar ve her ikincil anahtar ayrı bir kapsam kümesi
        ic = r.get("icerik") or {}
        kapsam.append(set(bh.slugla(" ".join([r["slug"], r.get("konu") or "", ic.get("anahtar") or "",
                                             ic.get("seo_baslik") or ""])).split("-")))
        for ik in ic.get("ikincil") or []:
            kapsam.append(set(bh.slugla(ik).split("-")))
    eklenen = []
    for c in adaylar:
        q = c["sorgu"]
        if MARKA.search(q) or not BILGI.search(q) or (c["s"] or 0) <= 10:
            continue
        kel = {w for w in bh.slugla(q).split("-") if len(w) > 2}
        if not kel or any(len(kel & s) / len(kel) >= 0.6 for s in kapsam):
            continue
        slug = bh.slugla(q)
        if len(slug) < 3:
            continue
        satir = {"slug": slug, "kaynak": "GSC", "plan_no": None, "oncelik": 800 + len(eklenen),
                 "konu": q, "tur": "NEW", "mevcut_slug": None, "kategori_id": None, "durum": "BEKLIYOR",
                 "kaynak_dosya": "raw.gsc_sorgu", "kaynak_sha": bh.slugla(q)[:16],
                 "icerik": {"plan": {"konu": q, "anahtar": q, "kanit": "GSC 35 gün: %s gösterim, sıra %s"
                                     % (c["g"], c["s"])}}, "bekleme_sebebi": None}
        r = k.ekle(satir)
        kapsam.append(kel)
        eklenen.append({"sorgu": q, "gosterim": c["g"], "sira": c["s"], "sonuc": r})
        if len(eklenen) >= int(os.environ.get("BLOG_KONU_HAFTALIK", "5")):
            break
    log("konu-bul:", json.dumps(eklenen, ensure_ascii=False))
    return {"eklenen": eklenen}


# ================================================================== YAZIM
def brif_metni() -> str:
    p = KAYNAK_DIR / "YAZIM-BRIFI.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def urun_gercekleri(metin: str) -> str:
    out = []
    for p in sorted((KAYNAK_DIR / "urun").glob("*.txt")):
        ad = p.stem.split("-", 1)[1].replace("-", " ")
        if re.search(r"(?i)\b" + re.escape(ad.split()[0]) + r"\b", metin):
            out.append("### %s\n%s" % (ad.upper(), p.read_text(encoding="utf-8")[:3500]))
    return "\n\n".join(out[:3])


def canli_metin(slug: str) -> str:
    kod, govde = bh.http_durum("%s/post/%s" % (bh.SITE, slug))
    if kod != 200:
        return ""
    return bh.duz_metin(govde)[:12000]


YAZIM_SEMA = """JSON nesnesi döndür (başka hiçbir şey yazma):
{"seo_baslik": "<=60 karakter", "meta": "140-155 karakter", "slug": "ascii-kucuk-harf-tire",
 "baslik": "H1 başlık", "anahtar": "birincil anahtar kelime", "ikincil": ["..."],
 "kategori": "icerik-sozlugu|botanik|bilincli-bakim|rituel|urun-rehber|formul|urun-kategori",
 "html": "gövde HTML (h1 YOK; yalnız p,h2,h3,ul,ol,li,table,thead,tbody,tr,th,td,a,strong,em). İlk paragraf 40-60 kelimelik doğrudan cevap. En az bir tablo. '<h2>Sık Sorulan Sorular</h2>' altında 4-6 soru (h3+p). En sonda '<h2>Kaynaklar</h2><ul><li>Yazar, yıl, başlık (İngilizce asıl başlık), dergi, PMID: ..., doi:...</li></ul>' 4-8 madde",
 "faq": [{"q": "...", "a": "..."}],
 "sahne_tr": "kapak için ürünsüz sahne tarifi (kış/mevsime uygun, Türk insanları varsa doğal)",
 "kesitler": ["kapakta gerçek fotoğrafı kullanılacak 0-2 ürün kesit adı, ör. hydravie"]}"""


def gemini_yaz(r: dict, ek_uyari: str = "") -> dict:
    plan = (r.get("icerik") or {}).get("plan") or {}
    mevcut = canli_metin(r["mevcut_slug"]) if r.get("mevcut_slug") else ""
    kesit_adlari = ", ".join(sorted(p.stem for p in bh.KESIT_DIR.glob("*.png")))
    istem = (
        "Sen L'CARLIÉ (Türk dermokozmetik markası) blogu için Türkçe SEO+GEO yazarı­sın. Aşağıdaki BAĞLAYICI brife "
        "harfiyen uy.\n\n# BRİF\n%s\n\n# KONU\nBaşlık önerisi: %s\nBirincil anahtar kelime: %s\nNotlar: %s\n"
        "İlgili ürünler: %s\n\n# ÜRÜN GERÇEKLERİ (yalnız bunlar ürüne yazılabilir)\n%s\n\n"
        "%s# KURALLAR (özet)\n- Gövde en az 1.300 kelime, dolgu yok.\n- Her bilimsel bilgi hakemli kaynağa dayanır; "
        "Google aramasıyla GERÇEK makaleleri bul; PMID ve DOI'yi yalnız doğruladıysan yaz. Uydurma kaynak "
        "yasak: kaynaklar otomatik olarak NCBI/Crossref'te başlıkla karşılaştırılacak, tutmayan silinecek.\n"
        "- Cümlenin nesnesi görünüm, his, doku, nem, konfor, koku, bakım olur. Ürün tedavi/iyileştirme/hastalık/"
        "vücut işlevi iddiası taşımaz. 'dermatolog önerir' yazılmaz. Olumsuz satış dili yok.\n"
        "- Ürün bağlantısı biçimi https://www.lcarlie.shop/product-page/<slug> (1-3 adet); MINISOOTH'a bağlantı yok.\n"
        "- Kesit adları: %s\n%s\n\n%s"
    ) % (brif_metni()[:6000], plan.get("konu") or r["konu"], plan.get("anahtar") or r["konu"],
         (plan.get("not") or "") + " " + (plan.get("kanit") or ""), plan.get("urun") or "-",
         urun_gercekleri(" ".join(str(v) for v in plan.values())) or "(ürün bağlamı yok: ürün adı verme)",
         ("# MEVCUT CANLI METİN (adres korunacak; bunu genişlet ve düzelt)\n%s\n\n" % mevcut) if mevcut else "",
         kesit_adlari, ek_uyari, YAZIM_SEMA)
    metin, model = bh.gemini(istem, modeller=bh.YAZI_MODELLERI, arama=True, json_cikti=False, en_cok=30000)
    d = bh.json_ayikla(metin)
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}}
        for x in d.get("faq") or [] if x.get("q") and x.get("a")]}
    slug = r["slug"]
    return {"plan_no": r.get("plan_no"), "slug": slug, "tur": r["tur"], "mevcut_slug": r.get("mevcut_slug"),
            "baslik": d.get("baslik") or plan.get("konu"), "seo_baslik": (d.get("seo_baslik") or "")[:70],
            "meta": d.get("meta") or "", "anahtar": d.get("anahtar") or plan.get("anahtar"),
            "ikincil": d.get("ikincil") or [], "kategori_id": bh.KATEGORI.get(d.get("kategori") or "", None),
            "faq_jsonld": faq, "html": re.sub(r"(?is)<h1[^>]*>.*?</h1>", "", d.get("html") or ""),
            "sahne_tr": d.get("sahne_tr") or plan.get("konu"),
            "kesitler": [x for x in (d.get("kesitler") or []) if (bh.KESIT_DIR / (x + ".png")).is_file()][:2],
            "yazan_model": model, "plan": plan}


def tr_kapilari(ic: dict) -> tuple[dict, dict]:
    """TR kapıları. (yeni_icerik, kapı_sonucu) döner; red -> KapiRed."""
    html, gunes = bh.gunes_uyarisi_ekle(ic["html"])
    sonuc = {"gunes_uyarisi_eklendi": gunes}
    sorun = bh.kelime_kapisi(html) + bh.yapi_kapisi(html)
    sonuc["kelime"] = bh.kelime_say(html)
    faq = ic.get("faq_jsonld") or {}
    nsoru = len(faq.get("mainEntity") or [])
    sonuc["sss"] = nsoru
    if nsoru < 3:
        sorun.append("SSS JSON-LD %d soru (<3)" % nsoru)
    idd = bh.iddia_kapisi(html, "tr")
    sonuc["iddia_red"], sonuc["iddia_kayit"] = idd["red"][:20], idd["kayit"][:20]
    if idd["red"]:
        sorun.append("iddia kapısı: %d red (ör. '%s' <- %s)" % (len(idd["red"]), idd["red"][0]["eslesen"],
                                                               idd["red"][0]["cumle"][:90]))
    kk = bh.kaynak_kapisi(html)
    sonuc["kaynak"] = {x: kk[x] for x in ("madde", "dogrulanan", "cikarilan", "ayrinti")}
    if kk["dogrulanan"] < bh.EN_AZ_KAYNAK:
        sorun.append("doğrulanan kaynak %d (< %d)" % (kk["dogrulanan"], bh.EN_AZ_KAYNAK))
    html = kk["html"]
    if sorun:
        sonuc["sorun"] = sorun
        raise bh.KapiRed(json.dumps(sonuc, ensure_ascii=False))
    ic = dict(ic, html=html)
    return ic, sonuc


# ================================================================== ÇEVİRİ
DIL_AD = {"en": "English", "de": "German", "ru": "Russian", "ar": "Arabic (Modern Standard)"}
CEVIRI_KURAL = """Translate this L'CARLIÉ skincare blog post from Turkish to {dil}. Return ONE JSON object only:
{{"baslik": "...", "seo_baslik": "<=60 chars", "meta": "140-160 chars", "slug": "lowercase-ascii-latin-words-with-hyphens (transliterate for ru/ar; keyword-rich in {dil})",
 "html": "translated body HTML", "faq": [{{"q": "...", "a": "..."}}], "kapak_metni": "the title, max 70 chars, for the cover image"}}
Rules:
- Keep EXACTLY the same HTML tags, structure, order and every href unchanged (same number of h2/h3/p/li/table/tr/td/a). Translate only text.
- Product names stay as written (HYDRAVIE, SUNACNEA SPF 30, BABY RESCUE, KINESIS+, L'CARLIÉ ...). INCI names stay in Latin/English.
- In the Sources/Kaynaklar list keep author names, journal, year, PMID, DOI and the original English article title verbatim; translate only the Turkish words around them; translate the heading "Kaynaklar" ({kaynak}).
- Use natural native wording that people really search in {dil}; primary keyword: "{anahtar}".
- Cosmetic regulation: sentences about the products may only describe appearance, feel, texture, moisture, comfort, scent and care. Never write that a product treats, heals, cures, repairs, prevents disease or changes body functions; no "dermatologist recommended", no "miracle". Do not add claims that are not in the Turkish text.
- Keep "consult your doctor" style sentences.
"""
KAYNAK_BASLIK = {"en": "Sources", "de": "Quellen", "ru": "Источники", "ar": "المصادر"}


def _etiket_sayim(html: str) -> dict:
    return {t: len(re.findall(r"(?i)<%s[\s>]" % t, html)) for t in ("h2", "h3", "table", "tr", "li", "a")}


def cevir(ic: dict, dil: str) -> tuple[dict, dict]:
    girdi = {"baslik": ic["baslik"], "seo_baslik": ic["seo_baslik"], "meta": ic["meta"], "html": ic["html"],
             "faq": [{"q": q["name"], "a": q["acceptedAnswer"]["text"]}
                     for q in (ic.get("faq_jsonld") or {}).get("mainEntity") or []]}
    istem = CEVIRI_KURAL.format(dil=DIL_AD[dil], kaynak=KAYNAK_BASLIK[dil], anahtar=ic.get("anahtar") or "") + \
        "\nINPUT JSON:\n" + json.dumps(girdi, ensure_ascii=False)
    son_sorun = []
    for _deneme in range(2):
        metin, model = bh.gemini(istem + ("\nPREVIOUS ATTEMPT PROBLEMS: %s" % son_sorun if son_sorun else ""),
                                 modeller=bh.CEVIRI_MODELLERI, json_cikti=True, en_cok=40000)
        try:
            d = bh.json_ayikla(metin)
        except (json.JSONDecodeError, ValueError):
            son_sorun = ["invalid JSON"]
            continue
        sorun = []
        a, b = _etiket_sayim(ic["html"]), _etiket_sayim(d.get("html") or "")
        for t in a:
            if abs(a[t] - b[t]) > (1 if t in ("li", "a") else 0):
                sorun.append("%s: %d != %d" % (t, b[t], a[t]))
        h1 = set(re.findall(r'href="([^"]+)"', ic["html"]))
        h2 = set(re.findall(r'href="([^"]+)"', d.get("html") or ""))
        if h1 != h2:
            sorun.append("href farkı: eksik %s fazla %s" % (sorted(h1 - h2)[:3], sorted(h2 - h1)[:3]))
        oran = len(bh.duz_metin(d.get("html") or "")) / max(1, len(bh.duz_metin(ic["html"])))
        if not 0.6 <= oran <= 1.9:
            sorun.append("uzunluk oranı %.2f" % oran)
        if not sorun:
            break
        son_sorun = sorun
    else:
        raise bh.KapiRed("çeviri %s yapı kapısı: %s" % (dil, "; ".join(son_sorun)))
    idd = bh.iddia_kapisi(d["html"] + " " + d.get("meta", ""), dil)
    if idd["red"]:
        raise bh.KapiRed("çeviri %s iddia kapısı: %s" % (dil, json.dumps(idd["red"][:3], ensure_ascii=False)))
    slug = (d.get("slug") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) or len(slug) > 90:
        slug = bh.slugla(slug) or (ic["slug"] + "-" + dil)
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": dil, "mainEntity": [
        {"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}}
        for x in d.get("faq") or [] if x.get("q") and x.get("a")]}
    return ({"baslik": d.get("baslik") or ic["baslik"], "seo_baslik": (d.get("seo_baslik") or "")[:70],
             "meta": (d.get("meta") or "")[:300], "slug": slug, "html": d["html"], "faq_jsonld": faq,
             "kapak_metni": (d.get("kapak_metni") or d.get("baslik") or "")[:90], "model": model},
            {"iddia_kayit": idd["kayit"][:5], "uzunluk": len(bh.duz_metin(d["html"]))})


# ================================================================== GÖRSEL
def nabiz() -> dict:
    k = bh.Kuyruk()
    ham = k.sql("SELECT coalesce(json_agg(x),'[]') FROM core.tarayici_nabiz_oku() x;")
    satirlar = json.loads(ham or "[]")
    if not satirlar:
        return {"durum": "RAPOR_YOK"}
    s = satirlar[0]
    ayr = s.get("ayrinti") or {}
    taze = float(s.get("yas_s") or 1e9) <= 300
    return {"durum": "TAZE" if taze else "BAYAT", "chrome": ayr.get("chrome"), "yas_s": s.get("yas_s")}


def sahne_istemi(ic: dict) -> str:
    istem = ("Translate this Turkish photo brief into ONE short English sentence describing only the setting, "
             "light, surfaces and props (ASCII only, no product, no packaging, no brand, no text). Return JSON "
             '{"sahne": "..."}. Brief: ' + (ic.get("sahne_tr") or ic["baslik"]))
    try:
        metin, _ = bh.gemini(istem, modeller=["gemini-3.5-flash", "gemini-flash-latest"], json_cikti=True,
                             en_cok=600, zaman=120)
        sahne = bh.json_ayikla(metin).get("sahne") or ""
    except Exception:  # noqa: BLE001
        sahne = ""
    sahne = re.sub(r"[^\x20-\x7e]", "", sahne).strip() or "a calm bathroom shelf with soft morning light"
    ay = simdi().month
    mevsim = ("winter in Turkey, cozy indoor light, knitwear and warm tones" if ay in (12, 1, 2)
              else "late autumn in Turkey, soft daylight, warm muted tones" if ay in (10, 11)
              else "spring in Turkey, fresh daylight" if ay in (3, 4, 5) else "summer in Turkey, bright natural light")
    return ("[L'CARLIE BLOG SCENE - new independent image, ignore earlier images in this chat] "
            "Create a photorealistic premium editorial photograph in landscape 3:2 format (1536x1024). "
            "Scene: %s Season and mood: %s. If people appear they are Turkish adults with natural, real-looking skin "
            "and modest everyday clothing, shown calmly. Composition: keep the left 45 percent of the frame calm, "
            "soft and simple (it will hold typeset text later) and keep an empty clean surface in the lower right "
            "third where a real product photo will be placed later. Show only the setting and props: the frame "
            "contains no bottles, tubes, jars, cosmetic packaging, labels, logos, letters or numbers. "
            "Natural light, shallow depth of field, muted warm palette, high detail." % (sahne, mevsim))


def gorsel_kuyruga(k: bh.Kuyruk, r: dict, kuru: bool) -> dict:
    from jarvis import tarayici
    ic = r["icerik"]
    istem = sahne_istemi(ic)
    n = int(r.get("gorsel_deneme") or 0) + 1
    if kuru:
        return {"istem": istem, "is_id": None, "kuru": True}
    s = tarayici.enqueue_browser_task(istem, "chatgpt_image", requested_by=ISTEYEN,
                                      idempotency_key="blog:%s:sahne:v%d" % (r["slug"], n))
    return {"istem": istem, "is_id": s["is_id"], "deneme": n, "kuyruga": simdi().isoformat()}


def gorsel_dizi(r: dict, sahne: str, kuru: bool) -> dict:
    ic = r["icerik"]
    hedef = (KURU_DIR if kuru else bh.YAYIN_DIR) / r["slug"]
    hedef.mkdir(parents=True, exist_ok=True)
    renk = bh.KATEGORI_RENK.get(r.get("kategori_id") or ic.get("kategori_id"), (176, 132, 96))
    kesitler = ic.get("kesitler") or []
    out = {"kapak": {}, "denetim": []}
    for dil in bh.TUM_DILLER:
        metin = ic["baslik"] if dil == "tr" else (r["ceviriler"][dil].get("kapak_metni") or r["ceviriler"][dil]["baslik"])
        yol = str(hedef / ("kapak-%s.jpg" % dil))
        bilgi = bh.kapak_diz(sahne, metin, dil, kesitler, renk, yol)
        out["kapak"][dil] = {"yol": yol, "url": "%s/%s/kapak-%s.jpg" % (bh.YAYIN_URL, r["slug"], dil),
                             "w": bilgi["w"], "h": bilgi["h"]}
        for ad, yer in zip(kesitler, bilgi["urun_yeri"], strict=False):
            out["denetim"].append({"dil": dil, "kesit": ad, "fark": bh.kesit_birebir_mi(yol, ad, yer)})
    yol = str(hedef / "ic.jpg")
    bilgi = bh.ic_gorsel_diz(sahne, kesitler[:1] or [], yol)
    out["ic"] = {"yol": yol, "url": "%s/%s/ic.jpg" % (bh.YAYIN_URL, r["slug"]), "w": bilgi["w"], "h": bilgi["h"]}
    # ambalaj kilidi ölçümü: yapıştırılan bölge kesitle birebir mi (JPEG kaybı payı 12)
    kotu = [x for x in out["denetim"] if x["fark"] > 12]
    if kotu:
        raise bh.KapiRed("ambalaj birebirlik ölçümü tutmadı: %s" % kotu[:3])
    return out


# ============================================================ YAYIN (Wix)
_LINK_DURUM: dict[str, int] = {}


def link_canli(url: str) -> bool:
    if url not in _LINK_DURUM:
        _LINK_DURUM[url] = bh.http_durum(url, 25)[0]
    return _LINK_DURUM[url] == 200


def link_cevirici(dil: str, kuyruk_harita: dict, kaldir: set):
    def cev(url: str) -> str | None:
        if url in kaldir:
            return None
        m = re.match(r"https://www\.lcarlie\.shop/(post|product-page)/([^?#]+)", url)
        if not m or dil == "tr":
            return url
        tip, s = m.groups()
        if tip == "post":
            hedef = kuyruk_harita.get(s, {}).get(dil)
            return "%s/%s/post/%s" % (bh.SITE, dil, hedef) if hedef else url
        aday = "%s/%s/product-page/%s" % (bh.SITE, dil, s)
        return aday if link_canli(aday) else url
    return cev


def kuyruk_harita(k: bh.Kuyruk) -> dict:
    """slug -> {dil: yayınlanmış çeviri slug'ı}"""
    h = {}
    for r in k.satirlar("durum = 'YAYINLANDI'"):
        h[r["slug"]] = {d: (r["wix"].get(d) or {}).get("slug") for d in bh.DILLER if (r["wix"].get(d) or {}).get("slug")}
    return h


def ic_linkler(html: str) -> list[str]:
    return sorted(set(u for u in re.findall(r'href="([^"]+)"', html) if "lcarlie.shop" in u))


def yayinla(k: bh.Kuyruk, r: dict, wix: bh.WixBlog, kuru: bool) -> dict:
    ic, slug = r["icerik"], r["slug"]
    g = r["gorsel"]
    durum = dict(r.get("wix") or {})
    # 1) iç bağlantı denetimi: canlıda 200 dönmeyen bağlantı geçici olarak kaldırılır
    kaldir = set(u for u in ic_linkler(ic["html"]) if not link_canli(u))
    if kaldir:
        k.olay(slug, "canlıda açılmayan bağlantı geçici kaldırıldı: %s" % sorted(kaldir))
    harita = kuyruk_harita(k)
    # 2) medya
    medya = dict(g.get("wix_medya") or {})
    for anahtar, bilgi in list(g["kapak"].items()) + [("ic", g["ic"])]:
        if anahtar in medya:
            continue
        medya[anahtar] = wix.medya_ice_al(bilgi["url"], "lc-blog-%s-%s.jpg" % (slug[:40], anahtar))
        if not kuru:
            k.guncelle(slug, gorsel={"wix_medya": medya})
    for fid in medya.values():
        wix.medya_hazir_bekle(fid)

    def draft(dil: str, metin: dict) -> dict:
        alt = ic.get("alt_1") if dil == "tr" else metin["baslik"]
        rich = bh.html_to_ricos(metin["html"], [{"id": medya["ic"], "width": g["ic"]["w"], "height": g["ic"]["h"],
                                                 "alt": alt or metin["baslik"], "sonra_h2": 2}],
                                link_cevir=link_cevirici(dil, harita, kaldir))
        hatalar = bh.ricos_denetle(rich)
        if hatalar:
            raise bh.KapiRed("Ricos öz-denetimi (%s): %s" % (dil, hatalar))
        kap = g["kapak"][dil]
        return {"title": metin["baslik"][:200], "excerpt": metin["meta"][:500], "memberId": bh.MEMBER_ID,
                "richContent": rich,
                "media": {"wixMedia": {"image": {"id": medya[dil], "width": kap["w"], "height": kap["h"]}},
                          "displayed": True, "custom": True, "altText": metin["baslik"][:150]},
                "seoData": bh.seo_verisi(metin["seo_baslik"] or metin["baslik"], metin["meta"],
                                         metin.get("faq_jsonld"), ic.get("anahtar") if dil == "tr" else "",
                                         ic.get("ikincil") or [] if dil == "tr" else [])}

    # 3) TR
    tr_metin = {"baslik": ic["baslik"], "seo_baslik": ic["seo_baslik"], "meta": ic["meta"], "html": ic["html"],
                "faq_jsonld": ic.get("faq_jsonld")}
    if "tr" not in durum:
        dp = draft("tr", tr_metin)
        if r["tur"] == "REFRESH":
            mevcut = wix.post_slugdan(r["mevcut_slug"] or slug)
            if not mevcut:
                raise bh.KapiRed("REFRESH: canlıda /post/%s bulunamadı" % (r["mevcut_slug"] or slug))
            pid = mevcut["id"]
            YEDEK_DIR.mkdir(parents=True, exist_ok=True)
            yedek = YEDEK_DIR / ("%s-tr-%s.json" % (slug, simdi().strftime("%Y%m%d%H%M%S")))
            yedek.write_text(json.dumps({"post": mevcut, "draft": wix.taslak(pid)}, ensure_ascii=False))
            dp.pop("seoSlug", None)
            if mevcut.get("categoryIds"):
                dp.pop("categoryIds", None)
            sonuc = wix.guncelle_yayinla(pid, dp)
            durum["tr"] = {"post_id": pid, "slug": mevcut.get("slug") or slug, "yedek": str(yedek),
                           "translationId": sonuc.get("translationId") or mevcut.get("translationId")}
        else:
            dp.update({"language": "tr", "seoSlug": slug,
                       "categoryIds": [r.get("kategori_id") or ic.get("kategori_id") or bh.KATEGORI["bilincli-bakim"]]})
            tas = wix.taslak_olustur(dp)
            pid = tas["id"]
            durum["tr"] = {"post_id": pid, "slug": slug}
            if not kuru:
                k.guncelle(slug, wix={"tr": durum["tr"]})
            wix.yayinla(pid)
        durum["tr"]["url"] = "%s/post/%s" % (bh.SITE, durum["tr"]["slug"])
        if kuru:
            (KURU_DIR / slug).mkdir(parents=True, exist_ok=True)
            (KURU_DIR / slug / "tr-draft.json").write_text(json.dumps(dp, ensure_ascii=False, indent=1))
        else:
            k.guncelle(slug, wix={"tr": durum["tr"]})
            k.olay(slug, "TR yayınlandı %s" % durum["tr"]["url"])
    pid = durum["tr"]["post_id"]
    # 4) çeviriler (Wix Multilingual: aynı translationId grubunda bağlı kopya)
    for dil in bh.DILLER:
        if dil in durum:
            continue
        metin = r["ceviriler"][dil]
        dp = draft(dil, metin)
        dp.pop("categoryIds", None)
        mevcut = None
        if r["tur"] == "REFRESH" and durum["tr"].get("translationId"):
            mevcut = wix.ceviri_bul(durum["tr"]["translationId"], dil)
        if mevcut:
            yedek = YEDEK_DIR / ("%s-%s-%s.json" % (slug, dil, simdi().strftime("%Y%m%d%H%M%S")))
            yedek.write_text(json.dumps(wix.taslak(mevcut["id"]), ensure_ascii=False))
            yeni_id, yeni_slug = mevcut["id"], mevcut.get("slug") or metin["slug"]
        else:
            kopya = wix.cevir_kopya(pid, dil)
            yeni_id, yeni_slug = kopya["id"], metin["slug"]
            dp["seoSlug"] = yeni_slug
            if not kuru:
                k.guncelle(slug, wix={dil: {"post_id": yeni_id, "slug": yeni_slug, "asama": "kopya"}})
        if kuru:
            (KURU_DIR / slug / ("%s-draft.json" % dil)).write_text(json.dumps(dp, ensure_ascii=False, indent=1))
        sonuc = wix.guncelle_yayinla(yeni_id, dp)
        if sonuc.get("seoSlug"):
            yeni_slug = sonuc["seoSlug"]
        durum[dil] = {"post_id": yeni_id, "slug": yeni_slug, "url": "%s/%s/post/%s" % (bh.SITE, dil, yeni_slug)}
        if not kuru:
            k.guncelle(slug, wix={dil: durum[dil]})
            k.olay(slug, "%s yayınlandı %s" % (dil, durum[dil]["url"]))
    # 5) sahip onaylı 301
    for kaynak in YONLENDIR.get(slug, []):
        if (durum.get("yonlendirme") or {}).get(kaynak):
            continue
        try:
            wix.yonlendirme(kaynak, "/post/%s" % durum["tr"]["slug"])
            durum.setdefault("yonlendirme", {})[kaynak] = "KURULDU"
        except bh.WixHata as e:
            durum.setdefault("yonlendirme", {})[kaynak] = "KURULAMADI: %s" % e
        if not kuru:
            k.guncelle(slug, wix={"yonlendirme": durum["yonlendirme"]})
    return {"wix": durum, "kaldirilan_linkler": sorted(kaldir)}


def canli_kontrol(r: dict, durum: dict) -> dict:
    out = {}
    for dil in bh.TUM_DILLER:
        if dil not in durum or not durum[dil].get("url"):
            continue
        bas = r["icerik"]["seo_baslik"] if dil == "tr" else r["ceviriler"][dil]["seo_baslik"]
        sonuc = None
        for _ in range(6):
            sonuc = bh.canli_denetle(durum[dil]["url"], bas)
            if sonuc["http"] == 200:
                break
            time.sleep(10)
        out[dil] = sonuc
    return out


# ================================================================ BİLDİRİM
def bildir(baslik: str, metin: str, etiket: str, eposta: bool = False) -> dict:
    from jarvis import haberci
    sonuc = {}
    try:
        sonuc["push"] = haberci.push_gonder(baslik, metin, etiket)
    except Exception as e:  # noqa: BLE001
        sonuc["push"] = "HATA %s" % str(e)[:100]
    if eposta:
        try:
            sonuc["eposta"] = haberci.eposta_gonder(baslik, metin)
        except Exception as e:  # noqa: BLE001
            sonuc["eposta"] = "HATA %s" % str(e)[:100]
    return sonuc


def gunde_bir(anahtar: str) -> bool:
    """Aynı anahtarla bugün bildirim gitti mi? Gitmediyse işaretler ve True döner."""
    DURUM_DIR.mkdir(parents=True, exist_ok=True)
    p = DURUM_DIR / ("bildirim-%s.json" % bugun())
    d = json.loads(p.read_text()) if p.is_file() else {}
    if anahtar in d:
        return False
    d[anahtar] = simdi().isoformat()
    p.write_text(json.dumps(d))
    return True


def insana(k: bh.Kuyruk, r: dict, sebep: str, kuru: bool) -> None:
    log("INSANA", r["slug"], sebep[:300])
    if kuru:
        return
    k.guncelle(r["slug"], durum="INSANA", bekleme_sebebi=sebep[:3000])
    k.olay(r["slug"], "INSANA: " + sebep[:300])
    if gunde_bir("insana-" + r["slug"]):
        bildir("Blog: yazı insana düştü", "%s — %s" % (r["konu"][:60], sebep[:200]), "blog-insana")


# ================================================================ ÇALIŞ
def adim(k: bh.Kuyruk, r: dict, a, wix_yetki: dict | None) -> str:
    slug, kuru = r["slug"], a.kuru
    d = r["durum"]
    if d == "BEKLIYOR":
        if r["kaynak"] == "HAZIR":
            ic = r["icerik"]
        else:
            ic = gemini_yaz(r)
            k.guncelle(slug, icerik=ic, deneme=int(r["deneme"]) + 1) if not kuru else None
        try:
            ic, kapi = tr_kapilari(ic)
        except bh.KapiRed as e:
            if r["kaynak"] != "HAZIR" and int(r["deneme"]) < 1 and "kelime" in str(e):
                ic = gemini_yaz(r, ek_uyari="ÖNCEKİ DENEME YETERSİZDİ: %s. Gövdeyi en az 1.400 kelimeye çıkar." % e)
                ic, kapi = tr_kapilari(ic)
            else:
                raise
        r["icerik"] = ic
        if kuru:
            (KURU_DIR / slug).mkdir(parents=True, exist_ok=True)
            (KURU_DIR / slug / "tr-kapi.json").write_text(json.dumps(kapi, ensure_ascii=False, indent=1))
            (KURU_DIR / slug / "tr.html").write_text(ic["html"])
        else:
            k.guncelle(slug, icerik=ic, kapilar={"tr": kapi}, durum="YAZILDI",
                       kategori_id=r.get("kategori_id") or ic.get("kategori_id"))
            k.olay(slug, "TR kapıları geçti: %s kelime, %s doğrulanmış kaynak" % (kapi["kelime"],
                                                                                kapi["kaynak"]["dogrulanan"]))
        r["durum"] = "YAZILDI"
        return "YAZILDI"
    if d == "YAZILDI":
        cev = dict(r.get("ceviriler") or {})
        for dil in bh.DILLER:
            if dil in cev and cev[dil].get("html"):
                continue
            metin, kapi = cevir(r["icerik"], dil)
            cev[dil] = metin
            if not kuru:
                k.guncelle(slug, ceviriler={dil: metin}, kapilar={"ceviri_" + dil: kapi})
            else:
                (KURU_DIR / slug).mkdir(parents=True, exist_ok=True)
                (KURU_DIR / slug / ("%s.json" % dil)).write_text(json.dumps(metin, ensure_ascii=False, indent=1))
            log(slug, dil, "çevrildi", metin["model"], metin["slug"])
        r["ceviriler"] = cev
        onceki_is = ((r.get("gorsel") or {}).get("is") or {})
        if onceki_is.get("is_id") and not kuru:
            # sahne işi zaten açılmış (ör. çeviri yeniden yapıldı): yeni iş açılmaz
            k.guncelle(slug, durum="GORSEL_BEKLIYOR")
            r["durum"] = "GORSEL_BEKLIYOR"
            return "GORSEL_BEKLIYOR"
        g = gorsel_kuyruga(k, r, kuru)
        if kuru:
            (KURU_DIR / slug / "sahne-istemi.txt").write_text(g["istem"])
            r["durum"] = "GORSEL_BEKLIYOR"
            return "GORSEL_BEKLIYOR(kuru)"
        k.guncelle(slug, gorsel={"is": g}, durum="GORSEL_BEKLIYOR", gorsel_deneme=g["deneme"],
                   bekleme_sebebi="ChatGPT sahnesi bekleniyor (tarayıcı işi %s)" % g["is_id"])
        k.olay(slug, "sahne işi kuyruğa: %s" % g["is_id"])
        r["durum"], r["gorsel_deneme"] = "GORSEL_BEKLIYOR", g["deneme"]
        r["gorsel"] = dict(r.get("gorsel") or {}, **{"is": g})
        return "GORSEL_BEKLIYOR"
    if d == "GORSEL_BEKLIYOR":
        from jarvis import tarayici
        is_ = ((r.get("gorsel") or {}).get("is") or {})
        sahne_yolu = a.sahne if getattr(a, "sahne", None) else None
        if not sahne_yolu:
            if not is_.get("is_id"):
                return "BEKLE(is yok)"
            durum = tarayici.isi_sonucu(int(is_["is_id"])) or {}
            if durum.get("durum") in ("BEKLIYOR", "CALISIYOR"):
                n = nabiz()
                if n["durum"] != "TAZE" or n.get("chrome") == "KAPALI":
                    if gunde_bir("worker-kapali") and not kuru:
                        bildir("Blog: görsel bekliyor", "Bilgisayardaki ChatGPT worker'ından haber yok ya da Chrome "
                               "kapalı (nabız %s, chrome %s). Blog yazıları görsel için bekliyor; start-chrome.ps1 "
                               "açılınca kendiliğinden devam eder." % (n["durum"], n.get("chrome")), "blog-worker")
                return "BEKLE(%s)" % durum.get("durum")
            if durum.get("durum") in ("HATA", "INSAN_GEREKLI") or (durum.get("durum") in ("BITTI", "SUNULDU")
                                                                     and not durum.get("sonuc_dosyalari")):
                hata = str(durum.get("hata") or "dosya yok")
                if durum.get("durum") != "SUNULDU":
                    tarayici._psql("SELECT core.tarayici_isi_sunuldu(:'is_id'::bigint, :'slug', 'GECTI');",
                                   "human_approver", degiskenler={"is_id": str(is_["is_id"]), "slug": "blog-%s" % is_["is_id"]})
                chrome_yok = "baglanilamadi" in hata or "Chrome" in hata[:60]
                if not chrome_yok and int(r.get("gorsel_deneme") or 0) >= GORSEL_EN_COK:
                    insana(k, r, "ChatGPT sahnesi %d denemede üretilemedi: %s" % (GORSEL_EN_COK, hata[:200]), kuru)
                    return "INSANA"
                n = nabiz()
                if chrome_yok and (n["durum"] != "TAZE" or n.get("chrome") == "KAPALI"):
                    if gunde_bir("worker-kapali") and not kuru:
                        bildir("Blog: görsel bekliyor", "ChatGPT worker'ı Chrome'a bağlanamıyor (chrome %s). "
                               "start-chrome.ps1 açılınca blog hattı kendiliğinden devam eder." % n.get("chrome"),
                               "blog-worker")
                    # Chrome yokken yeni iş açmak denemeyi yakar; bir sonraki koşuda tekrar bakılır
                    k.guncelle(slug, bekleme_sebebi="ChatGPT worker'ı Chrome'a bağlanamıyor; Chrome açılınca yeniden istenecek")
                    if n.get("chrome") == "KAPALI" or n["durum"] != "TAZE":
                        return "BEKLE(chrome yok)"
                if chrome_yok:  # Chrome geri geldi: deneme sayılmadan yeniden iste
                    r["gorsel_deneme"] = max(0, int(r.get("gorsel_deneme") or 0))
                g = gorsel_kuyruga(k, r, kuru)
                k.guncelle(slug, gorsel={"is": g}, gorsel_deneme=g["deneme"])
                r["gorsel_deneme"], r["gorsel"] = g["deneme"], dict(r.get("gorsel") or {}, **{"is": g})
                k.olay(slug, "sahne yeniden istendi (%s): %s" % (hata[:80], g["is_id"]))
                return "GORSEL_YENIDEN"
            dosyalar = durum.get("sonuc_dosyalari") or []
            sahne_yolu = str(tarayici.CIKTI_KOK / dosyalar[0])
            if durum.get("durum") == "BITTI":
                tarayici._psql("SELECT core.tarayici_isi_sunuldu(:'is_id'::bigint, :'slug', 'GECTI');",
                               "human_approver", degiskenler={"is_id": str(is_["is_id"]), "slug": "blog-%s" % is_["is_id"]})
        hedef = (KURU_DIR if kuru else bh.YAYIN_DIR) / slug
        hedef.mkdir(parents=True, exist_ok=True)
        sahne_kopya = bh.KOK / "sahne" / ("%s.png" % slug)
        sahne_kopya.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sahne_yolu, sahne_kopya)
        gd = gorsel_dizi(r, str(sahne_kopya), kuru)
        gd["sahne"] = str(sahne_kopya)
        r["gorsel"] = dict(r.get("gorsel") or {}, **gd)
        if not kuru:
            k.guncelle(slug, gorsel=gd, durum="GORSEL_HAZIR", bekleme_sebebi=None)
            k.olay(slug, "kapak x5 + iç görsel dizildi")
        r["durum"] = "GORSEL_HAZIR"
        return "GORSEL_HAZIR"
    if d == "GORSEL_HAZIR":
        if wix_yetki and not str(wix_yetki.get("blog_okuma", "")).startswith("VAR") and not kuru:
            sebep = ("Wix API anahtarında Blog/Medya izni yok (%s). Wix > Hesap Ayarları > API Anahtarları'nda "
                     "anahtara 'Wix Blog', 'Media Manager' ve 'SEO' izinleri eklenince kendiliğinden yayınlanır."
                     % json.dumps(wix_yetki, ensure_ascii=False))
            k.guncelle(slug, bekleme_sebebi=sebep)
            if gunde_bir("wix-yetki"):
                bildir("Blog: Wix izni gerekli", sebep[:300], "blog-wix", eposta=True)
            return "BEKLE(wix izni)"
        wix = bh.WixBlog(kuru=kuru)
        sonuc = yayinla(k, r, wix, kuru)
        if kuru:
            return "YAYIN(kuru)"
        canli = canli_kontrol(r, sonuc["wix"])
        k.guncelle(slug, kapilar={"canli": canli, "kaldirilan_linkler": sonuc["kaldirilan_linkler"]})
        if (canli.get("tr") or {}).get("http") != 200:
            raise bh.DisHata("TR yazı canlıda açılmadı: %s" % canli.get("tr"))
        k.guncelle(slug, durum="YAYINLANDI", yayinlandi="NOW()", bekleme_sebebi=None, hata=None)
        k.olay(slug, "YAYINLANDI: " + ", ".join("%s %s" % (d_, (c or {}).get("http")) for d_, c in canli.items()))
        return "YAYINLANDI"
    return "ATLA(%s)" % d


def link_onar(k: bh.Kuyruk, a) -> list:
    """Yayında geçici kaldırılmış bağlantıların hedefi artık canlıysa yazıyı yeniden yayınlar."""
    out = []
    for r in k.satirlar("durum = 'YAYINLANDI' AND jsonb_array_length(coalesce(kapilar->'kaldirilan_linkler','[]')) > 0"):
        bekleyen = r["kapilar"]["kaldirilan_linkler"]
        _LINK_DURUM.clear()
        if not all(link_canli(u) for u in bekleyen):
            continue
        if a.kuru:
            out.append(r["slug"])
            continue
        wix = bh.WixBlog()
        harita = kuyruk_harita(k)
        for dil in bh.TUM_DILLER:
            w = (r["wix"] or {}).get(dil) or {}
            if not w.get("post_id"):
                continue
            metin = r["icerik"] if dil == "tr" else r["ceviriler"][dil]
            g = r["gorsel"]
            rich = bh.html_to_ricos(metin["html"], [{"id": g["wix_medya"]["ic"], "width": g["ic"]["w"],
                                                     "height": g["ic"]["h"], "alt": metin["baslik"], "sonra_h2": 2}],
                                    link_cevir=link_cevirici(dil, harita, set()))
            wix.guncelle_yayinla(w["post_id"], {"richContent": rich, "memberId": bh.MEMBER_ID})
        k.guncelle(r["slug"], kapilar={"kaldirilan_linkler": []})
        k.olay(r["slug"], "geçici kaldırılan bağlantılar geri kondu: %s" % bekleyen)
        out.append(r["slug"])
    return out


def sira_sec(k: bh.Kuyruk, a) -> list[dict]:
    if a.slug:
        r = k.bir(a.slug)
        return [r] if r else []
    surecte = k.satirlar("durum IN ('YAZILDI','GORSEL_BEKLIYOR','GORSEL_HAZIR','HATA')",
                         sira="CASE durum WHEN 'GORSEL_HAZIR' THEN 0 WHEN 'GORSEL_BEKLIYOR' THEN 1 "
                              "WHEN 'YAZILDI' THEN 2 ELSE 3 END, oncelik, id")
    surecte = [r for r in surecte if r["durum"] != "HATA" or int(r["deneme"]) < 5]
    bugun_yayin = int(k.sql("SELECT count(*) FROM core.blog_kuyruk WHERE durum='YAYINLANDI' AND "
                            "(yayinlandi AT TIME ZONE 'Europe/Istanbul')::date = (now() AT TIME ZONE "
                            "'Europe/Istanbul')::date;") or 0)
    bos = TAVAN - bugun_yayin - len([r for r in surecte if r["durum"] != "HATA"])
    yeni = []
    if bos > 0:
        bekleyen = k.satirlar("durum = 'BEKLIYOR'")
        bekleyen_slug = {r["slug"]: r for r in bekleyen}
        for r in bekleyen:
            if len(yeni) >= bos:
                break
            # iç bağlantı bağımlılığı: hedef kuyrukta bekliyorsa önce o
            hedefler = [m for m in re.findall(r"lcarlie\.shop/post/([a-z0-9-]+)", (r["icerik"] or {}).get("html", ""))
                        if m in bekleyen_slug and m != r["slug"]]
            for h in hedefler:
                if len(yeni) < bos - 1 and bekleyen_slug[h] not in yeni:
                    yeni.append(bekleyen_slug[h])
            if r not in yeni and len(yeni) < bos:
                yeni.append(r)
    return surecte + yeni


def calis(a) -> dict:
    basla = simdi().isoformat()
    k = bh.Kuyruk(kuru=a.kuru)
    rapor = {"islenen": [], "hata": []}
    wix_yetki = None
    try:
        wix_yetki = bh.WixBlog().yetki()
    except Exception as e:  # noqa: BLE001
        wix_yetki = {"hata": str(e)[:200]}
    rapor["wix_yetki"] = wix_yetki
    secilen = sira_sec(k, a)
    for r in secilen:
        if r["durum"] in ("INSANA", "YAYINLANDI") and not a.slug:
            continue
        if r["durum"] == "HATA":
            r["durum"] = (r.get("kapilar") or {}).get("_son_durum") or "BEKLIYOR"
        onceki = None
        for _ in range(5):  # aynı koşuda ilerleyebildiği kadar ilerler
            onceki_durum = r["durum"]
            try:
                sonuc = adim(k, r, a, wix_yetki)
            except bh.KrediBitti as e:
                log("KREDI", r["slug"], str(e)[:300])
                rapor["hata"].append({"slug": r["slug"], "asama": onceki_durum, "hata": "KREDI: " + str(e)[:200]})
                if not a.kuru:
                    k.guncelle(r["slug"], bekleme_sebebi="Yazı modeli bekliyor: " + str(e)[:400])
                    if gunde_bir("kredi"):
                        bildir("Blog: yazı modeli bekliyor", "Blog yazısı üretilemedi: %s. Sorun giderilince "
                               "yazılar kendiliğinden devam eder." % str(e)[:300], "blog-kredi", eposta=True)
                break
            except bh.KapiRed as e:
                insana(k, r, str(e), a.kuru)
                rapor["islenen"].append({"slug": r["slug"], "sonuc": "INSANA", "sebep": str(e)[:300]})
                break
            except Exception as e:  # noqa: BLE001
                iz = traceback.format_exc()[-1500:]
                log("HATA", r["slug"], iz)
                rapor["hata"].append({"slug": r["slug"], "asama": onceki_durum, "hata": str(e)[:300]})
                if not a.kuru:
                    k.guncelle(r["slug"], durum="HATA", hata=("%s: %s" % (onceki_durum, e))[:2000],
                               deneme=int(r.get("deneme") or 0) + 1, kapilar={"_son_durum": onceki_durum})
                    if int(r.get("deneme") or 0) + 1 >= 5:
                        insana(k, r, "5 denemede dış hata: %s" % str(e)[:200], a.kuru)
                break
            rapor["islenen"].append({"slug": r["slug"], "sonuc": sonuc})
            log(r["slug"], onceki_durum, "->", sonuc)
            if sonuc.startswith(("BEKLE", "INSANA", "YAYINLANDI", "ATLA", "YAYIN(kuru)", "GORSEL_YENIDEN")) \
                    or sonuc == onceki or (sonuc == "GORSEL_BEKLIYOR(kuru)" and not a.sahne):
                break
            onceki = sonuc
    try:
        rapor["link_onar"] = link_onar(k, a)
    except Exception as e:  # noqa: BLE001
        rapor["hata"].append({"asama": "link_onar", "hata": str(e)[:200]})
    if not a.kuru:
        durum = "FAILED" if rapor["hata"] and not rapor["islenen"] else ("PARTIAL" if rapor["hata"] else
                                                                         ("SUCCESS" if rapor["islenen"] else "NO_DATA"))
        try:
            bh.yukleme_log("blog_hatti", durum, len(secilen), len([x for x in rapor["islenen"]
                                                                  if x["sonuc"] == "YAYINLANDI"]),
                           json.dumps(rapor, ensure_ascii=False)[:1000], basla)
        except Exception as e:  # noqa: BLE001
            log("yukleme_log yazılamadı:", e)
    print(json.dumps(rapor, ensure_ascii=False))
    return rapor


# ================================================================== RAPOR
def rapor(a) -> dict:
    k = bh.Kuyruk()
    bugun_yayin = k.satirlar("durum='YAYINLANDI' AND (yayinlandi AT TIME ZONE 'Europe/Istanbul')::date = "
                             "(now() AT TIME ZONE 'Europe/Istanbul')::date")
    bekleyen = k.satirlar("durum IN ('YAZILDI','GORSEL_BEKLIYOR','GORSEL_HAZIR','HATA')")
    insan = k.satirlar("durum='INSANA'")
    kalan = int(k.sql("SELECT count(*) FROM core.blog_kuyruk WHERE durum='BEKLIYOR';") or 0)
    sat = ["L'CARLIÉ blog hattı — %s" % bugun(), ""]
    sat.append("Bugün yayınlanan: %d" % len(bugun_yayin))
    for r in bugun_yayin:
        sat.append("• %s" % r["konu"])
        for d in bh.TUM_DILLER:
            u = ((r.get("wix") or {}).get(d) or {}).get("url")
            if u:
                sat.append("   %s: %s" % (d, u))
    sat.append("")
    sat.append("Süreçte: %d" % len(bekleyen))
    for r in bekleyen:
        sat.append("• %s — %s%s" % (r["konu"][:70], r["durum"], (": " + (r.get("bekleme_sebebi") or r.get("hata") or "")[:160])
                                    if (r.get("bekleme_sebebi") or r.get("hata")) else ""))
    sat.append("")
    sat.append("Sahibe düşen (yayınlanmadı): %d" % len(insan))
    for r in insan[:15]:
        sat.append("• %s — %s" % (r["konu"][:70], (r.get("bekleme_sebebi") or "")[:200]))
    sat.append("")
    sat.append("Kuyrukta sırada bekleyen konu: %d" % kalan)
    govde = "\n".join(sat)
    if a.kuru:
        print(govde)
        return {"metin": govde}
    ozet = "Bugün %d yazı yayında; süreçte %d, sahibe düşen %d." % (len(bugun_yayin), len(bekleyen), len(insan))
    sonuc = bildir("Blog hattı günlük rapor", ozet + "\n" + govde, "blog-rapor", eposta=True)
    print(json.dumps({"ozet": ozet, "bildirim": sonuc}, ensure_ascii=False))
    return sonuc


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("komut", choices=["yukle", "calis", "konu-bul", "rapor", "yetki"])
    p.add_argument("--kuru", action="store_true")
    p.add_argument("--slug")
    p.add_argument("--sahne", help="(test) ChatGPT yerine verilen sahne dosyasıyla diz")
    a = p.parse_args()
    if a.komut == "yukle":
        yukle(a)
    elif a.komut == "calis":
        r = calis(a)
        return 1 if r["hata"] and not r["islenen"] else 0
    elif a.komut == "konu-bul":
        konu_bul(a)
    elif a.komut == "rapor":
        rapor(a)
    elif a.komut == "yetki":
        print(json.dumps(bh.WixBlog().yetki(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
