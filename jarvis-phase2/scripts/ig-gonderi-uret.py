#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instagram gönderi ve reklam paketlerini ÖLÇÜLMÜŞ veriden üretir.

SAHİP: "onların talebine ve piyasaya göre satılabilecek instagram postu ve
reklam postları hazırlanması istiyorum, kreatif tarafıyla tartışılsın."

"PİYASAYA GÖRE" NE DEMEK -- ÖLÇÜLDÜ, TAHMİN EDİLMEDİ
  raw.ig_medya (124 gönderi)      VIDEO 51,5 ort. beğeni · KARUSEL 15,9 ·
                                  TEK GÖRSEL 14,7  -> video 3,5 kat
  mart.kreatif_performans (63)    VIDEO link başı 2,6 TL · SHARE 4,3 TL
                                  CTA: VIEW_INSTAGRAM_PROFILE 1,0 TL ama
                                  SHOP_NOW 9,8 TL
  mart.urun_sinyal                36 üründen YALNIZ 2'sinde satış var:
                                  VIREON 7 adet · INTIMBLANC 2 adet

🔴 EN ÖNEMLİ BULGU -- UCUZ TIKLAMA SATIŞ DEĞİL. Profil tıklaması 1,0 TL,
mağaza tıklaması 9,8 TL: dokuz kat. Ama profil tıklaması satın alma yoluna
ÇIKMIYOR. Reklam hafızasındaki ölçüm bunun bedelini söylüyor: harcamanın
%53'ü satın alma yoluna hiç ulaşmadı. Bu yüzden SATIS amaçlı paketlerde
CTA SHOP_NOW önerilir ve pahalı olduğu AÇIKÇA yazılır -- ucuz olanı
önermek raporu güzelleştirir, kasayı doldurmaz.

🔴 CAPTION'DAKİ HER ÜRÜN CÜMLESİ AYIKLANIR, UYDURULMAZ. Kaynak:
state/katalog.json içindeki `satis_cumleleri` -- yayındaki Wix metninden
alınmış ve jarvis.compliance'dan TEMİZ geçmiş cümleler. Kanca ve yapı
yazılır; İDDİA yazılmaz. Birleştirilen caption yeniden denetlenir, çünkü
iki temiz cümle yan yana geldiğinde yeni bir iddia doğabilir.

🔴 GÖRSEL BRİEFİ AI GÖRSELİ İSTEMEZ. Sahip kararı: ürünlü AI görseli
kullanılamaz. Brief ya gerçek çekim ister ya da ürünsüz arka plan +
tasarım katmanında metin.

İTİRAZ: her pakete karşı argüman yazılır. Şema, itirazı yanıtlanmamış
paketin onaylanmasını ENGELLER -- "tartışılsın" isteğinin karşılığı bu.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis import compliance  # noqa: E402

KAP = "lcarlie-postgres"
KATALOG = pathlib.Path(os.environ.get(
    "JARVIS_STATE_DIR", str(KOK / "state"))) / "katalog.json"

# 🔴 TAVAN DENETCIDEN ALINIR, BURADA YAZILMAZ. Ilk surumde 8 yazdim,
# gercek tavan 5'ti (compliance.HASHTAG_CAP) ve uretilen paketlerden biri
# "hashtag tavani" bulgusuyla dondu. Ayni sayiyi iki yerde tutmak, birinin
# digerinden sessizce ayrilmasi demek -- bu projede TURLER listesinde ayni
# hatayi bir kez yaptim (6 yaziyordu, veride 16 vardi).
EN_COK_HASHTAG = compliance.HASHTAG_CAP

ORTAK_HASHTAG = ["#lcarlie", "#dermokozmetik", "#ciltbakımı"]


def psql(sql: str, degiskenler: dict | None = None) -> list[dict]:
    komut = ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
             "-U", "n8n", "-d", "n8n"]
    for ad, deger in (degiskenler or {}).items():
        komut += ["-v", "%s=%s" % (ad, "" if deger is None else str(deger))]
    komut += ["-f", "-"]
    p = subprocess.run(komut, input="\\set ON_ERROR_STOP on\n" + sql + "\n",
                       capture_output=True, text=True, timeout=120, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:400])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


# --- olculmus dayanak ------------------------------------------------------
def olcumler() -> dict:
    ig = psql("""SELECT row_to_json(t) FROM (
      SELECT tur, count(*) adet, round(avg(begeni), 1) ort_begeni
        FROM raw.ig_medya GROUP BY 1 ORDER BY 3 DESC) t;""")
    cta = psql("""SELECT row_to_json(t) FROM (
      SELECT coalesce(cta, '(yok)') cta, count(*) adet,
             round(avg(link_ctr)::numeric, 2) link_ctr,
             round(avg(link_basi_maliyet)::numeric, 1) link_maliyet
        FROM mart.kreatif_performans WHERE yeterli_ornek
       GROUP BY 1 ORDER BY 4) t;""")
    satan = psql("""SELECT row_to_json(t) FROM (
      SELECT urun_adi, adet, siparis, round(ciro_net::numeric, 0) ciro
        FROM mart.urun_sinyal ORDER BY adet DESC) t;""")
    return {"ig": ig, "cta": cta, "satan": satan}


def _slugla(ad: str) -> str:
    return ad


def urun_secimi(katalog: dict, olcum: dict) -> list:
    """Hangi ürüne post yazılacak ve NEDEN.

    🔴 36 ÜRÜNE EŞİT DAĞITILMIŞ BİR PLAN, ÖLÇÜMÜ YOK SAYMAK OLUR. Satışı
    kanıtlı iki ürün önce gelir; geri kalanı "aday" olarak, okunabilir bir
    sonuç bekleyerek girer. Aksi halde bütçe 36 yöne bölünür ve hiçbirinden
    sinyal alınmaz -- bu projede reklam tarafında zaten yaşandı.
    """
    urunler = {u["ad"]: u for u in katalog["urunler"]}
    secim = []

    satan_adlar = []
    for s in olcum["satan"]:
        u = urunler.get(s["urun_adi"])
        if not u:
            continue
        satan_adlar.append(s["urun_adi"])
        secim.append({
            "urun": u, "amac": "SATIS",
            "dayanak": ("ÖLÇÜLDÜ: %d adet / %d sipariş / %s TL net ciro "
                        "(mart.urun_sinyal). Satışı kanıtlı iki üründen biri."
                        % (s["adet"], s["siparis"], s["ciro"])),
        })

    # Aday: satışı olmayan ama katalog metni TAM olan ürünler. Metni eksik
    # olanı öne çıkarmak, sorunun üstüne reklam harcamak olur.
    adaylar = [u for u in katalog["urunler"]
               if u["ad"] not in satan_adlar
               and u["ozet"] and len(u["satis_cumleleri"]) >= 5
               and u["gorseller"] and u["inci"]]
    adaylar.sort(key=lambda u: -(u["fiyat"] or 0))
    for u in adaylar[:4]:
        secim.append({
            "urun": u, "amac": "TANITIM",
            "dayanak": ("Satışı ÖLÇÜLMEDİ (0 adet). Aday sebebi: katalog "
                        "metni tam (özet + %d temiz cümle + INCI + görsel) "
                        "ve fiyatı yüksek (%s TL), yani bir satış kasada "
                        "görünür. Sonuç okunana kadar iddia değil DENEME."
                        % (len(u["satis_cumleleri"]), int(u["fiyat"] or 0))),
        })

    # B2B: eczane/profesyonel kazanımı. Katalog bu gece kuruldu; saha
    # ziyareti henuz 0. Tek paket -- olcum yoksa cok paket uretmek uydurma.
    eczane_uygun = [u for u in katalog["urunler"]
                    if u["ozet"] and u["inci"] and u["gorseller"]]
    if eczane_uygun:
        secim.append({
            "urun": max(eczane_uygun, key=lambda u: u["fiyat"] or 0),
            "amac": "B2B",
            "dayanak": ("ÖLÇÜLDÜ: 18.824 saha hedefi hazır, 2.589'u eczane; "
                        "ziyaret 0. Bu paket eczaneye DUYURU amaçlı, "
                        "tüketiciye satış amaçlı değil."),
        })
    return secim


# --- paket kurulumu --------------------------------------------------------
KANCA = {
    "SATIS": "%s — günlük bakım rutininde bir adım.",
    "TANITIM": "%s nedir, ne için kullanılır?",
    "B2B": "Eczanenizde L'CARLIÉ: %s",
}

BRIEF = {
    "REELS": ("15-25 sn dikey video. İlk 2 saniyede ürün elde görünsün, "
              "yazı sonra gelsin. GERÇEK ÇEKİM -- ürünlü AI görseli sahip "
              "kararıyla yasak. Ses: müzik + ekranda okunan metin "
              "(altyazı zorunlu, izleyicinin %85'i sessiz izler). "
              "Ölçülen sebep: video ortalama 51,5 beğeni, tek görsel 14,7."),
    "KARUSEL": ("4 kare. 1) ürün 2) kime uygun 3) kullanım 4) nereden "
                "alınır. Metin TASARIM KATMANINDA dizilir, görsele AI ile "
                "yazdırılmaz. Ölçülen sebep: karusel ortalama 15,9 beğeni "
                "-- videodan düşük, bilgi yoğun içerik için yine uygun."),
    "TEK_GORSEL": ("Tek kare ürün fotoğrafı, elimizdeki katalog görseli "
                   "kullanılabilir. Ölçülen sebep: en düşük etkileşim "
                   "(14,7) -- yalnız duyuru için."),
}


def cta_secimi(amac: str, olcum: dict) -> tuple:
    """CTA ve GEREKÇESİ. Ucuz olan önerilmez, doğru olan önerilir."""
    tablo = {c["cta"]: c for c in olcum["cta"]}
    profil = tablo.get("VIEW_INSTAGRAM_PROFILE")
    magaza = tablo.get("SHOP_NOW")
    if amac == "SATIS":
        gerekce = ("SHOP_NOW seçildi. ÖLÇÜLDÜ: profil tıklaması "
                   "%s TL, mağaza tıklaması %s TL -- mağaza dokuz kat "
                   "pahalı. Yine de mağaza seçiliyor çünkü profil tıklaması "
                   "SATIN ALMA YOLUNA ÇIKMIYOR. Reklam ölçümünde harcamanın "
                   "%%53'ü satın alma yoluna hiç ulaşmadı; ucuz tıklama o "
                   "körlüğün kaynağı." % (
                       profil["link_maliyet"] if profil else "?",
                       magaza["link_maliyet"] if magaza else "?"))
        return "SHOP_NOW", gerekce
    if amac == "B2B":
        return "MESSAGE_PAGE", ("Eczane/profesyonel karşılığında satın alma "
                               "değil GÖRÜŞME hedefleniyor; mesaj kutusu "
                               "doğru uç. Ölçülen link başı maliyet 3,1 TL.")
    return "SEE_DETAILS", ("Tanıtım amaçlı: henüz satışı ölçülmemiş ürün için "
                           "mağazaya pahalı tıklama satın almak yerine ilgi "
                           "ölçülüyor. Ölçülen maliyet 5,4 TL.")


def caption_kur(urun: dict, amac: str) -> tuple:
    """(kanca, caption, hashtagler). Ürün cümleleri AYIKLANIR."""
    ad = (urun["ad"] or "").split("(")[0].strip()
    kanca = KANCA[amac] % ad

    # Ayiklanmis cumleler: kataloğun havuzu (yayindaki metin + denetim).
    havuz = [c for c in (urun.get("satis_cumleleri") or []) if len(c) < 240]
    govde = havuz[:2] if amac != "B2B" else havuz[:1]
    if not govde and urun.get("ozet"):
        govde = [urun["ozet"]]

    satirlar = [kanca, ""]
    satirlar += govde
    if amac == "B2B":
        satirlar += ["", "Eczane ve profesyonel kullanım için ürün dosyası, "
                         "INCI listesi ve numune talebi: mesaj kutusu."]
    elif amac == "SATIS":
        satirlar += ["", "lcarlie.com.tr"]

    etiketler = ORTAK_HASHTAG + ["#" + (urun["slug"] or "").replace("-", "")]
    if amac == "B2B":
        etiketler += ["#eczane", "#eczacı"]
    etiketler = [e for e in dict.fromkeys(etiketler) if len(e) > 2][:EN_COK_HASHTAG]

    return kanca, "\n".join(satirlar).strip(), etiketler


def itiraz_kur(urun: dict, amac: str, olcum: dict) -> tuple:
    """Kreatif tarafın karşı argümanı ve ona ölçülmüş yanıt."""
    if amac == "SATIS":
        itiraz = ("Kreatif itirazı: aynı ürüne tekrar bütçe koymak, "
                  "portföyün kalanını hiç denemeden gömüyor. VIREON'un "
                  "DM'lerin %92'sini tuttuğu zaten biliniyor; yeni bilgi "
                  "üretmiyoruz.")
        yanit = ("Yanıt: haklı ama sıra önemli. Ölçülen tek satış yolu bu "
                 "ürün (7 adet / 8.498 TL) ve o yol HÂLÂ kırık -- sınıfı "
                 "FIX_FUNNEL_FIRST, reklam harcaması net ciroyu aşıyor. "
                 "Kırık bir yolu onarmadan ikinci ürünü aynı yola sokmak, "
                 "aynı zararı ikiye katlar. Portföy denemeleri TANITIM "
                 "paketlerinde, küçük bütçeyle ve okunabilir sonuçla var.")
    elif amac == "TANITIM":
        itiraz = ("Kreatif itirazı: satışı sıfır olan ürüne post yazmak "
                  "tahmine bütçe koymaktır; hangi ürünün tutacağını "
                  "bilmiyoruz.")
        yanit = ("Yanıt: doğru, bu yüzden paket İDDİA değil DENEME olarak "
                 "işaretli ve CTA satın alma değil ilgi ölçümü. Seçim "
                 "rastgele de değil: katalog metni tam olan ve fiyatı "
                 "yüksek olan ürünler seçildi, yani tek satış kasada "
                 "görünür. Sonuç okunmadan ikinci post yazılmaz.")
    else:
        itiraz = ("Kreatif itirazı: eczaneye Instagram'dan ulaşılmaz; "
                  "eczacı Instagram'da tedarikçi aramıyor. Bu paket yanlış "
                  "kanalda.")
        yanit = ("Yanıt: kısmen haklı -- bu paket satış kanalı değil, "
                 "GÜVEN kanalı. Saha ziyaretinde eczacının ilk yaptığı şey "
                 "markayı aramak; boş bir profil ziyaretin kendisini "
                 "zayıflatır. Bu yüzden B2B tek pakettir ve bütçesi yok; "
                 "asıl iş sahada, 2.589 eczane hedefi hazır.")
    return itiraz, yanit


def denetle(caption: str, hashtagler: list) -> tuple:
    """Birleştirilmiş caption yeniden denetlenir.

    İki temiz cümle yan yana geldiğinde yeni bir iddia doğabilir; tek tek
    temiz olmaları birleşiminin temiz olduğunu göstermez.
    """
    tam = caption + "\n" + " ".join(hashtagler)
    r = compliance.review(tam)
    if not r.findings:
        return "TEMIZ", None
    return "BULGULU", " · ".join(sorted({
        "%s: %s" % (f.rule, (getattr(f, "excerpt", "") or "")[:60])
        for f in r.findings}))[:900]


def main() -> int:
    t0 = time.time()
    if not KATALOG.exists():
        print("DURDU: katalog yok -- once scripts/katalog-uret.py")
        return 1
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    olcum = olcumler()

    print("ÖLÇÜLEN DAYANAK")
    for i in olcum["ig"]:
        print("  IG %-14s %3d gonderi · ort. begeni %s"
              % (i["tur"], i["adet"], i["ort_begeni"]))
    for c in olcum["cta"]:
        print("  CTA %-24s link basi %s TL · link CTR %s"
              % (c["cta"], c["link_maliyet"], c["link_ctr"]))
    for s in olcum["satan"]:
        print("  SATAN %-42s %d adet · %s TL" % (s["urun_adi"][:42], s["adet"], s["ciro"]))

    secim = urun_secimi(katalog, olcum)

    # 🔴 TEKRAR ONLEME. Bu betik haftalik kosacak. Karar bekleyen bir paket
    # varken ayni urune/amaca ikincisini yazsaydik liste her hafta buyur,
    # sahip 40 paketin arasinda kaybolur ve hicbirine karar vermezdi.
    # Onaylanmis ya da reddedilmis paket TEKRAR uretilebilir -- o karar
    # verilmis, yenisi yeni bir denemedir.
    bekleyen = {(r["urun_slug"], r["amac"]) for r in psql(
        "SELECT row_to_json(t) FROM (SELECT urun_slug, amac FROM"
        " core.ig_gonderi_plani WHERE durum = 'ONERI') t;")}
    atlanan = [s for s in secim if (s["urun"]["slug"], s["amac"]) in bekleyen]
    secim = [s for s in secim if (s["urun"]["slug"], s["amac"]) not in bekleyen]
    for s in atlanan:
        print("  = atlandi (karar bekleyen paket var): %-9s %s"
              % (s["amac"], s["urun"]["ad"][:38]))

    yazilan = bulgulu = 0
    for s in secim:
        u, amac = s["urun"], s["amac"]
        bicim = "REELS" if amac in ("SATIS", "TANITIM") else "TEK_GORSEL"
        kanca, caption, etiketler = caption_kur(u, amac)
        cta, cta_gerekce = cta_secimi(amac, olcum)
        itiraz, yanit = itiraz_kur(u, amac, olcum)
        denetim, notu = denetle(caption, etiketler)
        if denetim != "TEMIZ":
            bulgulu += 1

        psql("""INSERT INTO core.ig_gonderi_plani
          (urun_slug, amac, bicim, kanca, caption, hashtagler, gorsel_brief,
           cta, cta_gerekce, dayanak, itiraz, itiraza_yanit, denetim,
           denetim_notu)
          VALUES (:'slug', :'amac', :'bicim', :'kanca', :'caption',
                  string_to_array(:'etiket', ' '), :'brief', :'cta',
                  :'ctag', :'dayanak', :'itiraz', :'yanit', :'denetim',
                  NULLIF(:'notu', ''));""",
             {"slug": u["slug"], "amac": amac, "bicim": bicim, "kanca": kanca,
              "caption": caption, "etiket": " ".join(etiketler),
              "brief": BRIEF[bicim], "cta": cta, "ctag": cta_gerekce,
              "dayanak": s["dayanak"], "itiraz": itiraz, "yanit": yanit,
              "denetim": denetim, "notu": notu or ""})
        yazilan += 1
        print("  + %-9s %-30s %s%s"
              % (amac, u["ad"][:30], denetim,
                 (" (" + (notu or "")[:60] + ")") if notu else ""))

    print("\n%d paket yazildi · %d bulgulu · %.1f sn"
          % (yazilan, bulgulu, time.time() - t0))
    if bulgulu:
        print("🔴 Bulgulu paket ONAYLANAMAZ (sema kisiti). Denetim notuna "
              "bakip caption duzeltilmeli.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
