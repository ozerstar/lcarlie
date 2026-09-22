#!/usr/bin/env python3
"""L'CARLIE - BULGUDAN GOREV

Site nobeti (ve diger olcumler) findings.jsonl'e bulgu yaziyor ama
kimse okumuyordu. Bu betik bulguyu ISE cevirir:

    bulgu  ->  sartname dosyasi  ->  core.ai_bulgu_gorev_ac()
           ->  dongu bir ONERI uretir  ->  ONAY KUYRUGU  ->  sahip karar verir

🔴 ONAY KAPISI DEGISMEZ. Bu betik hicbir seyi uygulamaz, hicbir seyi
   onarmaz. Yalnizca "su bulguya bakilsin" diye is acar. Uygulama icin
   sahibin onayi gerekir - degisen tek sey NE UZERINDE calisilacagina
   kimin karar verdigi.

🔴 SINIRLAR BURADA DEGIL VERITABANINDA. Gunluk tavan, acik is tavani ve
   ayni bulgudan ikinci kez is acilamamasi core.ai_bulgu_gorev_ac()
   icinde zorlanir. Bu betik degistirilse bile tavanlar asilamaz.
   Buradaki suzgecler yalnizca GURULTU azaltir.

🔴 SESSIZ BASARISIZLIK YOK. Tavan dolduysa, yetki yoksa ya da fonksiyon
   kurulu degilse bu ayrica yazilir; "0 is acildi" ile "is acamadim"
   ayri seylerdir.

Kullanim:
  bulgu-gorev.py            Uygun bulgular icin is ac
  bulgu-gorev.py --kuru     Ne yapacagini yaz, HICBIR SEY yapma
  bulgu-gorev.py --sinir N  Tek kosuda en fazla N is (varsayilan 3)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

KOK = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
BULGU_DOSYA = KOK / "state" / "findings.jsonl"
SARTNAME_DIZIN = KOK / "state" / "agency" / "pending"
ISLENEN_DOSYA = KOK / "state" / "site-nobeti" / "islenen-bulgular.json"

# 🔴 IZINLI BULGU TIPLERI. Liste disindaki hicbir sinyal is acmaz.
#    Acik liste (allowlist) kullaniliyor: yeni bir sinyal kodu eklendiginde
#    kendiliginden is acmaya baslamasin, once bilincli olarak eklensin.
IZINLI_KODLAR = {"site_erisim", "site_seo", "site_gerileme"}
# INFO seviyesi is acmaz: bilgi notu icin insan mesaisi harcanmaz.
IZINLI_ONEM = {"CRITICAL", "WARNING"}

PSQL = ["docker", "exec", "-i", "lcarlie-postgres",
        "psql", "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1", "-tAc"]


def _slug(metin: str) -> str:
    """Imzadan dosya adina uygun, KARARLI bir slug uretir.

    Kararli olmasi sart: ayni bulgu her kosuda ayni slug'i vermezse
    veritabanindaki tekillik kontrolu ise yaramaz ve ayni 404 her gun
    yeni bir is acar.
    """
    d = unicodedata.normalize("NFKD", metin)
    d = d.encode("ascii", "ignore").decode("ascii").lower()
    d = re.sub(r"[^a-z0-9]+", "-", d).strip("-")
    return (d or "bulgu")[:60].rstrip("-")


def _islenenler() -> set[str]:
    try:
        return set(json.loads(ISLENEN_DOSYA.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _islenen_yaz(kume: set[str]) -> None:
    ISLENEN_DOSYA.parent.mkdir(parents=True, exist_ok=True)
    ISLENEN_DOSYA.write_text(json.dumps(sorted(kume), ensure_ascii=False, indent=1),
                             encoding="utf-8")


def _bulgular() -> list[dict]:
    """findings.jsonl'in son kismi. Ayni imzadan EN YENISI alinir."""
    try:
        satirlar = BULGU_DOSYA.read_text(encoding="utf-8").splitlines()[-400:]
    except OSError:
        return []
    enyeni: dict[str, dict] = {}
    for s in satirlar:
        try:
            d = json.loads(s)
        except ValueError:
            continue
        imza = d.get("signature")
        if imza:
            enyeni[imza] = d
    return list(enyeni.values())


def _sablon(sebep: str) -> str:
    """Sebepten adres ve sayilari cikarir; geriye SABLON kalir.

    "/category/x HTTP 404 donuyor." ve "/category/y HTTP 404 donuyor."
    ayni sablona iner. "TLS sertifikasi 12 gun sonra bitiyor" inmez -
    sablonu farklidir ve ayri bir olgudur.
    """
    t = re.sub(r"https?://\S+", "<adres>", sebep)
    t = re.sub(r"/\S+", "<yol>", t)
    t = re.sub(r"\d+", "<n>", t)
    return re.sub(r"\s+", " ", t).strip()


def _grupla(bulgular: list[dict]) -> list[dict]:
    """Ayni sablonu paylasan bulgulari TEK bulguya indirir.

    🔴 Gruplanmazsa ayni sorun kuyruga defalarca duser. 23 kategori
       sayfasinin 404 dondugu TEK bir olgudur: kategori sayfasi yayinda
       degil. Sahip buna bir kez bakmali, 23 kez degil.
    """
    kova: dict[tuple, list[dict]] = {}
    for b in bulgular:
        anahtar = (b.get("signal_code"), b.get("severity"), _sablon(b.get("reason", "")))
        kova.setdefault(anahtar, []).append(b)

    sonuc: list[dict] = []
    for (kod, onem, sablon), grup in kova.items():
        if len(grup) == 1:
            sonuc.append(grup[0])
            continue
        adresler = [str((g.get("evidence") or {}).get("url") or "") for g in grup]
        adresler = [a for a in adresler if a]
        ornek = "\n".join("  - " + a for a in sorted(adresler)[:12])
        if len(adresler) > 12:
            ornek += f"\n  - ... ve {len(adresler) - 12} adres daha"
        sonuc.append({
            # Imza grubun TAMAMINI temsil eder: ayni grup ikinci kez is acmaz.
            "signature": f"{kod}:grup:{_slug(sablon)}:{len(grup)}",
            "reason": (f"{len(grup)} adres ayni sorunu gosteriyor: {sablon}\n\n"
                       f"Etkilenen adresler:\n{ornek}"),
            "evidence": {"grup_sayisi": len(grup), "sablon": sablon,
                         "adresler": sorted(adresler)[:40]},
            "signal_code": kod,
            "severity": onem,
            "observed_at": max((g.get("observed_at") or "") for g in grup),
        })
    return sonuc


def _sartname_yaz(slug: str, bulgu: dict) -> Path:
    """Donguyun okuyacagi sartname.

    Bicim agency_store.load_spec() ile ayni: state/agency/pending/<slug>.json
    ve icinde dolu bir `payload`. `reason` dogrudan payload'a yazilir ki
    dongu kendi yer tutucusunu KOYMASIN - onaylayan insan ilk o metni
    gorur ve orada ne oldugu yazmalidir.
    """
    SARTNAME_DIZIN.mkdir(parents=True, exist_ok=True)
    kanit = bulgu.get("evidence") or {}
    satirlar = [
        bulgu.get("reason", ""),
        "",
        f"Onem     : {bulgu.get('severity', '?')}",
        f"Sinyal   : {bulgu.get('signal_code', '?')}",
        f"Olculdu  : {bulgu.get('observed_at', '?')}",
    ]
    if kanit.get("url"):
        satirlar.append(f"Adres    : {kanit['url']}")
    satirlar += [
        "",
        "Kanit    : " + json.dumps(kanit, ensure_ascii=False)[:600],
        "",
        "Bu oneri site nobeti olcumunden otomatik acildi. Hicbir degisiklik "
        "YAPILMADI; onaylanirsa ne yapilacagi ayrica kararlastirilir.",
    ]
    spec = {
        "product": "Site nöbeti",
        "concept_name": (bulgu.get("reason") or "")[:70],
        "kaynak": "site-nobeti",
        "signature": bulgu.get("signature"),
        "payload": {
            "subject_ref": f"bulgu:{slug}",
            "reason": "\n".join(satirlar)[:3500],
        },
    }
    yol = SARTNAME_DIZIN / f"{slug}.json"
    yol.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return yol


def _gorev_ac(slug: str, sebep: str) -> tuple[str | None, str | None]:
    """(task_id, hata). Ikisi de None ise: zaten acilmis."""
    sql = ("SELECT core.ai_bulgu_gorev_ac("
           + _sql_metin(slug) + ", " + _sql_metin(sebep) + ");")
    try:
        p = subprocess.run(PSQL + [sql], capture_output=True, text=True, timeout=60)
    except subprocess.SubprocessError as e:
        return None, f"psql calistirilamadi: {e}"
    if p.returncode != 0:
        return None, (p.stderr or p.stdout).strip().splitlines()[-1][:200]
    cikti = p.stdout.strip()
    return (cikti or None), None


def _sql_metin(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulgudan gorev acar")
    ap.add_argument("--kuru", action="store_true", help="hicbir sey yapma, yalniz yaz")
    ap.add_argument("--sinir", type=int, default=3, help="tek kosuda en fazla is")
    a = ap.parse_args()

    islenen = _islenenler()
    # 🔴 ONCE GRUPLA, SONRA SUZ. Ters sirada yapilirsa grup imzasi
    #    "islenen" kumesiyle karsilastirilmadan once olusur ve ayni grup
    #    her kosuda yeniden aday olur.
    aday = [b for b in _grupla(_bulgular())
            if b.get("signal_code") in IZINLI_KODLAR
            and b.get("severity") in IZINLI_ONEM
            and b.get("signature") not in islenen]
    # En onemliden basla: CRITICAL once.
    aday.sort(key=lambda b: 0 if b.get("severity") == "CRITICAL" else 1)

    print(f"=== BULGUDAN GOREV === uygun bulgu: {len(aday)} · sinir: {a.sinir}")
    if not aday:
        print("  is acilacak yeni bulgu yok.")
        return 0

    acilan = atlanan = 0
    hatalar: list[str] = []
    for bulgu in aday[: a.sinir]:
        imza = bulgu["signature"]
        slug = _slug(imza)
        sebep = (bulgu.get("reason") or "")[:480]
        if len(sebep) < 40:
            # Veritabani zaten reddeder; burada sebebi yazip geciyoruz.
            print(f"  ATLA  {slug}: sebep 40 karakterden kisa")
            atlanan += 1
            continue
        if a.kuru:
            print(f"  [KURU] {slug}  <- {sebep[:70]}")
            continue
        _sartname_yaz(slug, bulgu)
        task_id, hata = _gorev_ac(slug, sebep)
        if hata:
            # 🔴 Sessizce gecme: tavan dolmasi da yetki eksigi de burada yazilir.
            print(f"  HATA  {slug}: {hata}")
            hatalar.append(hata)
            continue
        islenen.add(imza)
        if task_id:
            print(f"  ACILDI gorev #{task_id}  {slug}")
            acilan += 1
        else:
            print(f"  ZATEN  {slug} icin is daha once acilmis")
            atlanan += 1

    if not a.kuru:
        _islenen_yaz(islenen)
    print(f"--- acilan: {acilan}  atlanan: {atlanan}  hata: {len(hatalar)}")
    # Hata varsa cikis kodu 1: zamanlayici gunlugunde gorunsun.
    return 1 if hatalar else 0


if __name__ == "__main__":
    sys.exit(main())
