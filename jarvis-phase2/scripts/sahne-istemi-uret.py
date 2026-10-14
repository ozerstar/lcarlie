#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Konseptten AYRINTILI sahne istemi yazar.

Sahip 26.09: "promptları detaylı oluştur."

🔴 HAKLI, VE EKSİĞİ ÖLÇTÜM. Konsept aşaması dokuz ayrı sanat yönetimi
alanı üretiyordu -- kamera (Arri Alexa Mini LF, 50mm, f/2.8), ışık (tek
kaynak, 5600K, sert yan vuruş), malzeme, ortam, derinlik, negatif alan,
yerleşim, renk paleti. Higgsfield'a gönderdiğim istem bunların HİÇBİRİNİ
taşımıyordu; yalnız iki satırlık özeti gidiyordu. Ürettiğim ayrıntıyı
kullanmadan attım.

🔴 VE BİR KUSUR DAHA: ürün havada duruyordu. Sahibin kendi yazdığı
istemde şu vardı -- "a clean uncluttered flat surface across the lower
third of the frame WHERE AN OBJECT WILL BE PLACED LATER". Benimkinde
yoktu. Sahnede ürünün oturacağı yüzey istenmezse, ürün sahneye
oturmuyor; kompozit yapıştırılmış duruyor. Artık YÜZEY ZORUNLU bir
madde.

İstem modele yazdırılır ama serbest bırakılmaz: aşağıdaki maddelerin
hepsi çıktıda ARANIR, biri eksikse istem REDDEDİLİR. Modelden "iyi bir
istem" rica edip gelene bakmamak, bugün düzelttiğimiz hatanın aynısı
olurdu.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis.model_layer import ModelRouter  # noqa: E402

KAP = "lcarlie-postgres"

# Ciktida ARANAN maddeler. Model bunlari atlarsa istem reddedilir.
# (anahtar, etiket, desenler)
ZORUNLU = [
    ("yuzey", "ürünün oturacağı yüzey",
     [r"\bsurface\b", r"\bplinth\b", r"\bledge\b", r"\bshelf\b",
      r"\bcounter\b", r"\btabletop\b", r"\bfloor\b"]),
    ("yerlestirme", "ürün sonradan yerleştirilecek notu",
     [r"placed later", r"will be placed", r"for product placement",
      r"reserved for the product", r"where the product"]),
    ("bos_alan", "tipografi için boş alan",
     [r"negative space", r"empty space", r"clear space"]),
    ("kamera", "kamera / lens",
     [r"\bmm\b", r"\blens\b", r"\bf/\d"]),
    ("isik", "ışık yönü ve niteliği",
     [r"\blight", r"\blit\b", r"\bshadow"]),
    ("gercekci", "fotoğraf, illüstrasyon değil",
     [r"photoreal", r"photographic", r"\bphoto\b"]),
    # Sahibin isteminden ogrenildi: AI gorselini ele veren sey
    # cozunurluk degil KUSURSUZLUK. Kusur ACIKCA istenmeli.
    ("kusur", "gerçek yüzey kusuru",
     [r"imperfect", r"\bdust\b", r"\bwear\b", r"\bslub",
      r"uneven", r"not perfectly uniform", r"nothing perfectly uniform"]),
    ("cgi_karsiti", "CGI karşıtı olumsuzlar",
     [r"no cgi", r"no 3d render", r"no hdr", r"no plastic"]),
    # Uretilen karede ayakli studyo lambasi cikti; istem bunu
    # yasaklamiyordu. Sahibin isteminde "no lamp, no light fixture"
    # vardi -- kopyalamayi atlamisim.
    ("ekipman_yok", "set ekipmanı yasağı",
     [r"no lamp", r"no light fixture", r"no studio equipment",
      r"no tripod", r"no softbox"]),
    ("olumsuz", "yasak listesi",
     [r"\bno product", r"\bno bottle", r"\bwithout any product"]),
]

SISTEM = """You write scene prompts for a luxury dermocosmetics brand's
advertising photography. The generated image is a SET, not a product shot:
the real product photograph is composited in afterwards by a separate
engine, and all typography is typeset afterwards in the brand's own fonts.

Therefore the prompt you write MUST:
1. Describe an EMPTY scene. No product, no bottle, no jar, no tube, no
   pump, no packaging, no label, no box, no cosmetic object of any kind.
2. Include a clean, uncluttered SURFACE (plinth, ledge, counter, floor
   or tabletop) at a stated position, explicitly noted as the place where
   a product will be placed later. Without this the composited product
   floats and looks pasted on.
3. Reserve a stated region as empty negative space for typography.
4. State camera: lens focal length, aperture, angle.
5. State lighting: number of sources, colour temperature, direction,
   shadow quality.
6. State materials, environment, depth of field and colour palette.
7. State that it is photographic and photorealistic, not an illustration
   or a 3D render. Name a camera body and lens, an aperture, the camera
   height and tilt, and a film grain reference.
8. Describe the light by its QUALITY and DIRECTION, never by its
   hardware. Say soft or hard, its direction, how far the shadow edge
   takes to fall off, any colour temperature drift across the frame.
   NEVER name a softbox, a bounce card, a light stand, a lamp or any
   fixture: the model draws whatever you name, and the equipment then
   appears in the photograph. This was measured -- a prompt reading
   \"a single 90x120cm softbox at 45 degrees and a large white bounce
   card low on the right\" produced a frame with a softbox on a stand at
   the upper left and a white panel at the right.
9. Ask for REAL SURFACE IMPERFECTION and say nothing should be perfectly
   uniform: settled dust, uneven wear, weave slubs, slightly off-centre
   composition, imperfect symmetry. This is what separates a photograph
   from a render; without it the frame reads as CGI however sharp it is.
10. End with an explicit exclusion list: no products, no bottles, no
   jars, no tubes, no packaging, no labels, no text, no letters, no
   words, no logos, no watermarks, no people, no hands, no faces, and
   also no CGI look, no 3D render, no HDR, no glow, no oversaturation,
   no plastic surfaces, and no visible set equipment: no lamp, no light
   fixture, no softbox, no tripod, no light stand, no cable, no camera.
   The lighting must be felt, never seen. Plus any cliche the brief
   rejects.

Write ONE English paragraph of 130-200 words. No headings, no bullet
points, no preamble. Output the prompt text only."""


def calistir(sql: str) -> list:
    p = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=sql, capture_output=True, text=True, timeout=60, check=False)
    if p.returncode:
        raise SystemExit("psql: " + (p.stderr or p.stdout)[:400])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip()]


def eksikleri_bul(istem: str) -> list:
    duz = istem.lower()
    eksik = []
    for _anahtar, etiket, desenler in ZORUNLU:
        if not any(re.search(d, duz) for d in desenler):
            eksik.append(etiket)
    return eksik


def istem_yaz(yonlendirici, k: dict, guclu: bool) -> str:
    istek = json.dumps({
        "konsept": k["ad"],
        "ana_fikir": k["ana_fikir"],
        "gorsel_metafor": k["gorsel_metafor"],
        "kompozisyon": k["kompozisyon"],
        "odak": k["odak"],
        "duygu": k["duygu"],
        "sanat_yonetimi": {
            "kamera": k.get("ay_kamera"), "isik": k.get("ay_isik"),
            "malzeme": k.get("ay_malzeme"), "ortam": k.get("ay_ortam"),
            "derinlik": k.get("ay_derinlik"),
            "negatif_alan": k.get("ay_negatif_alan"),
            "yerlesim": k.get("ay_yerlesim"), "renk": k.get("ay_renk")},
        "format": "vertical 9:16" if k["bicim"] == "REELS" else "square 1:1",
        "not": "Bu alanlar TURKCE. Ingilizce isteme cevir ve HEPSINI kullan.",
    }, ensure_ascii=False)
    sonuc, kademe, _ = yonlendirici.generate(
        [{"role": "system", "content": SISTEM},
         {"role": "user", "content": istek}],
        900, escalate=guclu, is_anahtari="sahne_istemi")
    metin = ((sonuc or {}).get("text") or (sonuc or {}).get("content") or "")
    return metin.strip(), kademe


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_id", nargs="*", type=int)
    ap.add_argument("--guclu", action="store_true")
    ap.add_argument("--deneme", type=int, default=2,
                    help="eksik madde varsa kac kez yeniden yazdirilsin")
    a = ap.parse_args()

    kosul = ""
    if a.plan_id:
        kosul = " AND plan_id IN (%s)" % ",".join(str(p) for p in a.plan_id)
    konseptler = calistir("""SELECT row_to_json(t) FROM (
      SELECT k.plan_id, p.urun_slug, p.bicim, k.ad, k.ana_fikir,
             k.gorsel_metafor, k.kompozisyon, k.odak, k.duygu,
             k.ay_kamera, k.ay_isik, k.ay_malzeme, k.ay_ortam,
             k.ay_derinlik, k.ay_negatif_alan, k.ay_yerlesim, k.ay_renk
        FROM core.kreatif_konsept k
        JOIN core.ig_gonderi_plani p USING (plan_id)
       WHERE k.secildi%s ORDER BY k.plan_id) t;""" % kosul)
    if not konseptler:
        raise SystemExit("secilen konsept yok")

    yonlendirici = ModelRouter()
    cikti = []
    for k in konseptler:
        print("\n=== paket %s · %s · %s ==="
              % (k["plan_id"], k["urun_slug"], k["ad"]))
        istem = None
        for deneme in range(1, a.deneme + 1):
            aday, kademe = istem_yaz(yonlendirici, k, a.guclu)
            eksik = eksikleri_bul(aday)
            print("  deneme %d (%s): %d kelime, eksik: %s"
                  % (deneme, kademe, len(aday.split()),
                     ", ".join(eksik) if eksik else "yok"))
            if not eksik:
                istem = aday
                break
        if istem is None:
            print("  🔴 ISTEM REDDEDILDI -- zorunlu madde eksik kaldi.")
            print("     Modelden istem rica edip gelene bakmamak,")
            print("     bugun duzelttigimiz hatanin aynisi olurdu.")
            continue
        print("\n" + istem + "\n")
        cikti.append({"plan_id": k["plan_id"], "urun": k["urun_slug"],
                      "konsept": k["ad"], "istem": istem})

    if cikti:
        yol = Path("/opt/lcarlie/higgsfield-gelen/istemler.json")
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps(cikti, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print("%d istem yazildi: %s" % (len(cikti), yol))
    return 0 if cikti else 3


if __name__ == "__main__":
    sys.exit(main())
