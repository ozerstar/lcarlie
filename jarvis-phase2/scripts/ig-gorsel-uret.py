#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gönderi paketlerine TASLAK görsel üretir.

Paketler `ig-gonderi-uret.py` tarafından ölçülmüş veriden yazılıyordu ama
görselleri yoktu: sahip metni okuyup "nasıl görünecek" sorusunu kafasında
canlandırmak zorundaydı. Bu betik o boşluğu kapatır.

ÜÇ KATMAN, `gorsel-kompozit.py` motoru:
  ürün  = katalog fotoğrafının pikselleri (rembg maskesi, gövde tam opak)
  sahne = düz/gradyan zemin (AI sahnesi verilirse o kullanılır)
  dizgi = Metropolis .otf, glif koruması açık

🔴 REELS BİR VİDEODUR; ÜRETİLEN KARE ONUN KAPAĞIDIR. Bunu "reels hazır"
diye raporlamak yanlış olurdu -- kapak, videonun kendisi değildir. Rapor
alanına açıkça `KAPAK` yazılır.

🔴 GÖRSEL ONAY YERİNE GEÇMEZ. Paket hâlâ ONERI durumunda kalır; görsel
yalnız kararı kolaylaştırır. Görseller kullanıcının ChatGPT web oturumunda üretilir; GPT ürün fotoğrafını
yeniden oluşturabileceği için piksel-birebirlik iddiası yapılmaz. Departman ve
insan incelemesi tamamlanmadan yayınlanmaz.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import time

KOK = pathlib.Path(__file__).resolve().parents[1]
KAP = "lcarlie-postgres"
CIKTI = pathlib.Path("/opt/lcarlie/gonderi-gorsel")

sys.path.insert(0, str(KOK))
_sp = importlib.util.spec_from_file_location(
    "gorsel_kompozit", str(KOK / "scripts" / "gorsel-kompozit.py"))
gk = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(gk)
_gs = importlib.util.spec_from_file_location(
    "gorsel_uret_gpt", str(KOK / "scripts" / "gorsel-uret.py"))
gpt_gorsel = importlib.util.module_from_spec(_gs)
_gs.loader.exec_module(gpt_gorsel)

# Paket biçimi -> görsel biçimi. REELS video olduğu için kapak karesi
# yine 9:16 üretilir.
BICIM_ESLEME = {"REELS": "REELS", "KARUSEL": "AKIS", "TEK_GORSEL": "KARE",
                "STORY": "REELS"}  # story de 9:16


def psql(sql: str, degiskenler: dict | None = None) -> list:
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


def alt_metin(paket: dict) -> str:
    """Görselin alt satırı: caption'ın İLK cümlesi.

    Uydurulmuş bir satır yazmıyoruz -- caption zaten yayındaki metinden
    ayıklanmış ve mevzuat denetiminden geçmiş cümlelerden kurulu.
    """
    for satir in (paket.get("caption") or "").split("\n"):
        s = satir.strip()
        if s and s != (paket.get("kanca") or "").strip() and not s.startswith("#"):
            return s if len(s) <= 110 else s[:107].rsplit(" ", 1)[0] + "…"
    return ""


def main() -> int:
    t0 = time.time()
    # Keep old files as an audit trail, but detach images from content that is
    # not explicitly approved by the content director and compliance gate.
    ayrilan = psql("""UPDATE core.ig_gonderi_plani
       SET gorsel_rapor = coalesce(gorsel_rapor, '{}'::jsonb) || jsonb_build_object(\n           'detached_image', gorsel_dosya, 'detached_reason', 'content_not_approved'),\n           gorsel_dosya = NULL
     WHERE gorsel_dosya IS NOT NULL
       AND (uzman_karari IS DISTINCT FROM 'GECER' OR denetim IS DISTINCT FROM 'TEMIZ')
     RETURNING json_build_object('plan_id', plan_id, 'uzman_karari', uzman_karari,
                                 'denetim', denetim, 'dosya', gorsel_dosya);""")
    if ayrilan:
        print("detached %d image links from unapproved posts; files retained for audit"
              % len(ayrilan))
    paketler = psql("""SELECT row_to_json(t) FROM (
      SELECT plan_id, urun_slug, amac, bicim, kanca, caption, gorsel_brief, gorsel_dosya
        FROM core.ig_gonderi_plani
       WHERE durum IN ('ONERI', 'ONAYLANDI') AND uzman_karari = 'GECER'
         AND denetim = 'TEMIZ' AND gorsel_dosya IS NULL
       ORDER BY plan_id) t;""")
    if not paketler:
        print("gorseli olmayan paket yok")
        return 0

    CIKTI.mkdir(parents=True, exist_ok=True)
    uretilen = hatali = 0
    for p in paketler:
        bicim = BICIM_ESLEME.get(p["bicim"], "AKIS")
        baslik = (p.get("kanca") or "").split("—")[0].strip() or p["urun_slug"]
        try:
            oran = {"REELS": "9:16", "AKIS": "4:5", "KARE": "1:1"}.get(bicim, "4:5")
            istem = (p.get("gorsel_brief") or "Premium, minimal, brand-safe editorial skincare studio.")
            urun_yolu, _kaynak = gk.urun_kaynagi(p["urun_slug"])
            istem = (
                f"Create a finished premium {oran} L'Carlie skincare social ad. "
                "IMAGE 1 is the real product photo; IMAGE 2 is the official logo. "
                "Use both as references, preserve the product's white color and visible package design. "
                "Compose a distinctive premium editorial beauty campaign with the product and logo; "
                "use a concept specific to the product, with tactile materials, considered depth, "
                "and deliberate lighting. Avoid stock-ad templates, generic gradients and cliché splashes. "
                "Do not add claims, prices, badges, or extra copy. Pair a refined editorial display face "
                "for the headline with a premium grotesk for the support line; precise kerning, optical "
                "alignment, purposeful line breaks, never default heavy geometric bold. Use the exact "
                "Turkish headline and support line, legibly and safely inside the crop. "
                f"Headline: {baslik}. Support line: {alt_metin(p)}. "
                f"Art direction: {istem}. Aspect ratio {oran}.")
            kare = gpt_gorsel.chatgpt_web_gorsel(
                istem, oran, [urun_yolu, gpt_gorsel.VARLIK / "logo" / "lcarlie-logo.png"])
            sahne_dizin = CIKTI
            sahne_dizin.mkdir(parents=True, exist_ok=True)
            ad = "jarvis-gpt-web-%s-%s.jpg" % (p["urun_slug"], str(p["plan_id"]))
            cikti_yolu = CIKTI / ad
            kare.save(cikti_yolu, "JPEG", quality=93)
            rapor = {"dosya": ad, "saglayici": "chatgpt_web_work",
                     "urun_kaynagi": str(urun_yolu), "urun_pikseli_birebir": False,
                     "inceleme_durumu": "TASARIM_INCELEMESI_BEKLIYOR"}
        except (gk.GorselHatasi, OSError, RuntimeError, ValueError) as hata:
            print("  HATA plan %s (%s): %s" % (p["plan_id"], p["urun_slug"], hata))
            hatali += 1
            continue

        # GPT referans urunu yeniden olusturabilir; piksel-birebirlik iddiasi yok.
        # Taslak insan ve tasarim incelemesi olmadan yayina gecmez.
        rapor["kapak_mi"] = p["bicim"] == "REELS"
        rapor["inceleme_durumu"] = "TASARIM_INCELEMESI_BEKLIYOR"
        rapor["not"] = "Görsel taslaktır; yayın için insan ve tasarım incelemesi gerekir."
        psql("""UPDATE core.ig_gonderi_plani
                   SET gorsel_dosya = :'dosya', gorsel_rapor = :'rapor'::jsonb
                 WHERE plan_id = %d;""" % int(p["plan_id"]),
             {"dosya": rapor["dosya"],
              "rapor": json.dumps(rapor, ensure_ascii=False)})
        uretilen += 1
        print("  + plan %-3s %-9s %-7s %-34s birebir %s%s"
              % (p["plan_id"], p["amac"], bicim, rapor["dosya"][:34],
                 "GPT-referans",
                 "  (REELS KAPAGI -- video degil)" if p["bicim"] == "REELS" else ""))

    print("\n%d gorsel · %d hatali · %.1f sn · %s"
          % (uretilen, hatali, time.time() - t0, CIKTI))
    return 0 if not hatali else 2


if __name__ == "__main__":
    raise SystemExit(main())
