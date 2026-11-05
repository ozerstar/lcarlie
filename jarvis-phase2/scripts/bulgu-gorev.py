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


def _sigdir(metin: str, sinir: int) -> str:
    """Paragraf sınırında keser ve kesildiğini yazar (jarvis.sinirlar.kisalt ile aynı kural)."""
    if len(metin) <= sinir:
        return metin
    kes = metin[: sinir - 40]
    yer = kes.rfind("\n")
    return (kes[:yer] if yer > sinir * 0.6 else kes).rstrip() + "\n… (kısaltıldı)"
from pathlib import Path

KOK = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
BULGU_DOSYA = KOK / "state" / "findings.jsonl"
SARTNAME_DIZIN = KOK / "state" / "agency" / "pending"
ISLENEN_DOSYA = KOK / "state" / "site-nobeti" / "islenen-bulgular.json"

# 🔴 IZINLI BULGU TIPLERI. Liste disindaki hicbir sinyal is acmaz.
#    Acik liste (allowlist) kullaniliyor: yeni bir sinyal kodu eklendiginde
#    kendiliginden is acmaya baslamasin, once bilincli olarak eklensin.
IZINLI_KODLAR = {
    # --- Wix sitesi: tespit + oneri. Onarim bizim depodan YAPILAMAZ;
    #     acilan is "su sayfa Wix editorunde yayinlansin" der, kod yazmaz.
    "site_erisim", "site_seo", "site_gerileme",
    # --- Panel: BIZIM depomuzda, yani CodingExecutor'un onarabilecegi yer.
    #     22.09.2026 sahip karari: "tamirci bosta durmasin, paneli onarsin".
    "panel_erisim", "panel_butunluk",
}
# INFO seviyesi is acmaz: bilgi notu icin insan mesaisi harcanmaz.
IZINLI_ONEM = {"CRITICAL", "WARNING"}

# 🔴 YAZIM KURALI (sahip 05.11.2026: "acikca yazmasini soylemistim ama hep
#    karisik"). Sahibe giden metin uc soruyu bu sirayla cevaplar: NE OLDU,
#    NE ANLAMA GELIYOR, NE YAPILMALI. Icinde sinyal kodu, sablon isareti
#    (<yol>, <n>), ham JSON, Ingilizce hata metni ve UTC saati OLMAZ.
#    tests/test_bulgu_gorev.py::AcikYazim bunu kilitler.
SINYAL = {
    "site_erisim": ("Siteye erişim",
                    "Müşteri bu sayfayı açamıyor olabilir; reklamdan ya da Google'dan gelen ziyaretçi kaybolur.",
                    "Sayfayı telefondan açıp dene. Açılmıyorsa Wix'te sayfanın yayında olduğunu kontrol et ya da Claude'a ilet."),
    "site_seo": ("Google görünürlüğü",
                 "Sayfa açılıyor ama Google'da eksik ya da hiç görünmeyebilir.",
                 "Wix'te sayfanın SEO ayarlarına (başlık, açıklama, arama motorlarına açık mı) bak ya da Claude'a ilet."),
    "site_gerileme": ("Sitede beklenmeyen değişiklik",
                      "Sayfa önceki ölçüme göre değişti. Bilerek yapılmadıysa bir şey bozulmuş olabilir.",
                      "Sayfayı aç ve içeriğin tam yüklendiğini kontrol et. Değişikliği sen yaptıysan bu kaydı reddetmen yeterli."),
    "panel_erisim": ("Jarvis paneline erişim",
                     "Jarvis paneli açılmıyor olabilir; onay ve raporlar görünmez.",
                     "Claude'a ilet; panel bizim sunucumuzda, onarımı oradan yapılır."),
    "panel_butunluk": ("Jarvis panelinin bütünlüğü",
                       "Panel açılıyor ama bir dosyası eksik ya da yanlış sürüm olabilir.",
                       "Claude'a ilet; son yayın kontrol edilmeli."),
}
ONEM_TR = {"CRITICAL": "Kritik", "WARNING": "Uyarı", "INFO": "Bilgi"}


def _tr_saat(iso: str) -> str:
    """UTC ISO zamani Turkiye saatine cevirir; okunamazsa oldugu gibi birakir."""
    import datetime as dt
    try:
        an = dt.datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso or "bilinmiyor")
    if an.tzinfo is None:
        an = an.replace(tzinfo=dt.timezone.utc)
    return an.astimezone(dt.timezone(dt.timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")

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
    return [row for row in enyeni.values() if row.get("status") != "RESOLVED"]


def _sablon(sebep: str) -> str:
    """Sebepten adres ve sayilari cikarir; geriye SABLON kalir.

    "/category/x HTTP 404 donuyor." ve "/category/y HTTP 404 donuyor."
    ayni sablona iner. "TLS sertifikasi 12 gun sonra bitiyor" inmez -
    sablonu farklidir ve ayri bir olgudur.
    """
    # 🔴 Burada bir de `https?://\S+ -> <adres>` satiri vardi; mutasyon
    #    testi onu silince HICBIR test patlamadi. Sebep esdeger mutasyon:
    #    URL'ler '/' icerdigi icin asagidaki desen zaten onlari da yutuyor
    #    ('https://a.example/p' -> 'https:<yol>'). Katkisi olmayan satir
    #    kaldirildi; testler aynen geciyor, davranis degismedi.
    t = re.sub(r"/\S+", "<yol>", sebep)
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
        # Sablon (<yol>, <n>) yalniz gruplama anahtari; sahibe GOSTERILMEZ.
        ilk = sorted(grup, key=lambda g: str((g.get("evidence") or {}).get("url") or ""))[0]
        sonuc.append({
            # Imza grubun TAMAMINI temsil eder: ayni grup ikinci kez is acmaz.
            "signature": f"{kod}:grup:{_slug(sablon)}:{len(grup)}",
            "reason": (f"{len(grup)} sayfada aynı sorun var. Örnek: {ilk.get('reason', '')}\n\n"
                       f"Etkilenen sayfalar:\n{ornek}"),
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
    konu, anlam, yapilacak = SINYAL.get(bulgu.get("signal_code"),
        ("Site nöbeti bulgusu", "Ölçümde beklenmeyen bir sonuç çıktı.", "Claude'a ilet."))
    satirlar = ["NE OLDU", bulgu.get("reason", "")]
    if kanit.get("url"):
        satirlar.append(f"Adres: {kanit['url']}")
    satirlar += [
        "",
        "NE ANLAMA GELİYOR", anlam,
        "",
        "NE YAPILMALI", yapilacak,
        "",
        f"Konu: {konu} · Önem: {ONEM_TR.get(bulgu.get('severity'), 'Belirsiz')} · "
        f"Ölçüm: {_tr_saat(bulgu.get('observed_at'))} (Türkiye saati)",
        "",
        "Bu kayıt site nöbetinin otomatik ölçümünden açıldı. Hiçbir şey değiştirilmedi; "
        "onaylarsan ne yapılacağına ayrıca karar verilir.",
    ]
    spec = {
        "product": "Site nöbeti",
        "concept_name": (bulgu.get("reason") or "")[:70],
        "kaynak": "site-nobeti",
        "signature": bulgu.get("signature"),
        "payload": {
            "subject_ref": f"bulgu:{slug}",
            # core.ai_propose_action reason <= 2000; aşınca öneri HİÇ yazılmıyordu (04.11).
            "reason": _sigdir("\n".join(satirlar), 1950),
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
        return None, (p.stderr or p.stdout).strip()[:1200]
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
