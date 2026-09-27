# -*- coding: utf-8 -*-
"""Kutu gerçeğindeki INCI listelerini core.urun_inci'ye yükler.

🔴 NEDEN AYRI BİR YÜKLEYİCİ. Veri JSON dosyalarında duruyor ve elle
   SQL'e çevirmek tırnak/kaçış hatasına açık. Bu projede kabuk
   tırnaklaması defalarca bozdu; yük stdin'den, dolar-tırnaklı JSON
   olarak gider -- `_gonderi_notu_ekle` ile aynı desen.

🔴 EKSİK ÜRÜN DE YAZILIR. INCI bölümü boş olan ürün `inci=NULL` ile
   kaydedilir. Satırı hiç yazmamak, "bu ürünü hiç görmedik" ile
   "gördük ama bilgisi yok"u karıştırırdı.

Kullanım:  python3 inci-yukle.py [--kuru]
           --kuru : hiçbir şey yazmaz, ne yapacağını söyler
"""
import glob
import json
import os
import secrets
import subprocess
import sys

KLASOR = "/opt/lcarlie/jarvis-phase2/varliklar/kutu-gercegi"
KAP = "lcarlie-postgres"


def kutu_gercekleri() -> list[dict]:
    """Her ürün için bir kayıt. Okunamayan dosya SESSİZCE ATLANMAZ."""
    kayitlar, sorunlu = [], []
    for yol in sorted(glob.glob(os.path.join(KLASOR, "*.json"))):
        ad = os.path.basename(yol)[:-5]
        # '_hepsi' toplu dosyadır, ürün değil.
        if ad.startswith("_"):
            continue
        try:
            with open(yol, encoding="utf-8") as dosya:
                veri = json.load(dosya)
        except (OSError, ValueError) as hata:
            sorunlu.append((ad, str(hata)[:80]))
            continue
        if not isinstance(veri, dict):
            sorunlu.append((ad, "kok " + type(veri).__name__))
            continue
        bolumler = veri.get("bolumler")
        if not isinstance(bolumler, dict):
            sorunlu.append((ad, "bolumler " + type(bolumler).__name__))
            continue
        ham = bolumler.get("inci")
        inci = str(ham).strip() if ham and str(ham).strip() else None
        kayitlar.append({
            "urun_anahtari": veri.get("urun_anahtari") or ad,
            "urun_adi": veri.get("urun_adi") or ad,
            "inci": inci,
            "kaynak": veri.get("kaynak"),
            "kaynak_tur": veri.get("kaynak_tur"),
        })
    return kayitlar, sorunlu


def yaz(kayitlar: list[dict]) -> int:
    yuk = json.dumps(kayitlar, ensure_ascii=False)
    etiket = "inci" + secrets.token_hex(6)
    if f"${etiket}$" in yuk:
        raise SystemExit("kodlama cakismasi, yazilmadi")
    sql = (
        "\\set ON_ERROR_STOP on\n"
        "BEGIN;\n"
        "SET SESSION AUTHORIZATION human_approver;\n"
        "INSERT INTO core.urun_inci"
        " (urun_anahtari, urun_adi, inci, kaynak, kaynak_tur, guncelleme)\n"
        "SELECT j->>'urun_anahtari', j->>'urun_adi', j->>'inci',\n"
        "       j->>'kaynak', j->>'kaynak_tur', now()\n"
        f"  FROM jsonb_array_elements(${etiket}${yuk}${etiket}$::jsonb) AS j\n"
        "ON CONFLICT (urun_anahtari) DO UPDATE SET\n"
        "  urun_adi   = EXCLUDED.urun_adi,\n"
        # 🔴 `IS DISTINCT FROM` degil dogrudan atama: kutu gercegi
        #    tek dogruluk kaynagi. Orada bosalmissa burada da bosalir.
        "  inci       = EXCLUDED.inci,\n"
        "  kaynak     = EXCLUDED.kaynak,\n"
        "  kaynak_tur = EXCLUDED.kaynak_tur,\n"
        "  guncelleme = now();\n"
        "COMMIT;\n")
    r = subprocess.run(
        ["docker", "exec", "-i", KAP, "psql", "-U", "n8n", "-d", "n8n"],
        input=sql, text=True, capture_output=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("psql hatasi: " + (r.stderr or "")[:400])
    return len(kayitlar)


def main() -> None:
    kayitlar, sorunlu = kutu_gercekleri()
    dolu = sum(1 for k in kayitlar if k["inci"])
    print("okunan urun      : %d" % len(kayitlar))
    print("  inci DOLU      : %d" % dolu)
    print("  inci YOK       : %d  %s" % (
        len(kayitlar) - dolu,
        [k["urun_anahtari"] for k in kayitlar if not k["inci"]]))
    if sorunlu:
        # 🔴 Sorunlu dosya sessizce atlanmaz; sayisi ve sebebi yazilir.
        print("  OKUNAMAYAN     : %d  %s" % (len(sorunlu), sorunlu))
    if "--kuru" in sys.argv:
        print("kuru kosu -- yazilmadi")
        return
    if not kayitlar:
        raise SystemExit("okunacak kayit yok -- yazilmadi")
    print("yazildi: %d satir" % yaz(kayitlar))


if __name__ == "__main__":
    main()
