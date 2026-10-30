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
yalnız kararı kolaylaştırır. Üretilen her görselin yanında ürün
pikselinin korunduğunu gösteren ölçüm (birebir oran + SSIM) saklanır.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import time

KOK = pathlib.Path(__file__).resolve().parents[1]
KAP = "lcarlie-postgres"
CIKTI = pathlib.Path("/opt/lcarlie/gonderi-gorsel")

_sp = importlib.util.spec_from_file_location(
    "gorsel_kompozit", str(KOK / "scripts" / "gorsel-kompozit.py"))
gk = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(gk)

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
    paketler = psql("""SELECT row_to_json(t) FROM (
      SELECT plan_id, urun_slug, amac, bicim, kanca, caption, gorsel_dosya
        FROM core.ig_gonderi_plani
       WHERE durum IN ('ONERI', 'ONAYLANDI') AND gorsel_dosya IS NULL
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
            rapor = gk.uret(p["urun_slug"], bicim=bicim, baslik=baslik,
                            alt=alt_metin(p), cikti_dizin=CIKTI)
        except gk.GorselHatasi as hata:
            print("  HATA plan %s (%s): %s" % (p["plan_id"], p["urun_slug"], hata))
            hatali += 1
            continue

        # 🔴 URUN PIKSELI KORUNMADIYSA KAYDEDILMEZ. Gorsel diskte kalir ama
        # pakete baglanmaz: kullanilabilir sayilan bir sey degil, bakilacak
        # bir kanittir.
        if (rapor.get("birebir_oran") or 0) < 0.999:
            print("  RED plan %s: urun pikseli degismis (birebir %s)"
                  % (p["plan_id"], rapor.get("birebir_oran")))
            hatali += 1
            continue

        rapor["kapak_mi"] = p["bicim"] == "REELS"
        psql("""UPDATE core.ig_gonderi_plani
                   SET gorsel_dosya = :'dosya', gorsel_rapor = :'rapor'::jsonb
                 WHERE plan_id = %d;""" % int(p["plan_id"]),
             {"dosya": rapor["dosya"],
              "rapor": json.dumps(rapor, ensure_ascii=False)})
        uretilen += 1
        print("  + plan %-3s %-9s %-7s %-34s birebir %s%s"
              % (p["plan_id"], p["amac"], bicim, rapor["dosya"][:34],
                 rapor["birebir_oran"],
                 "  (REELS KAPAGI -- video degil)" if p["bicim"] == "REELS" else ""))

    print("\n%d gorsel · %d hatali · %.1f sn · %s"
          % (uretilen, hatali, time.time() - t0, CIKTI))
    return 0 if not hatali else 2


if __name__ == "__main__":
    raise SystemExit(main())
