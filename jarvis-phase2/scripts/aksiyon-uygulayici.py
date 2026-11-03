#!/usr/bin/env python3
"""L'CARLIE - AKSIYON UYGULAYICI: onaylanmis isi dis dunyaya yazar.

ZINCIRDEKI YERI
    oneri (Jarvis / sistem dedektoru)  ->  SAHIP ONAYI (panel, parmak izi)
        ->  core.ai_action_execution OPEN  ->  ** BU BETIK **  ->  platform
        ->  platformdan GERI OKU  ->  EXECUTED / FAILED

🔴 ONAYSIZ HICBIR SEY UYGULANMAZ. Bu betik yalniz core.ai_claim_approved_action_tipli()
   ile APPROVED durumdaki isi alir; oneri uretmez, onay vermez.

🔴 "GONDERDIM" != "UYGULANDI". 21.09'da Trendyol'a giden guncelleme SUCCESS
   dondu ama hicbir sey degismedi. Her uygulayici yazdiktan sonra degeri
   platformdan GERI OKUR; okunan deger beklenenle ayni degilse is EXECUTED
   sayilmaz, FAILED_FINAL olur ve sebebi yazilir.

🔴 UC FREN, HEPSI UYGULAMADAN ONCE:
   1. core.ai_orchestrator_config.uygulayici_acik = false -> hic is kapilmaz
   2. core.ai_action_tavan_dolu() -> tur icin gunluk adet/tutar tavani
      (satiri olmayan tur UYGULANMAZ)
   3. tur basina sozlesme kontrolu (payload alanlari, sinirlar)

🔴 TAVAN DOLUYSA IS YANMAZ: FAILED_RETRYABLE doner, ertesi gun yeniden denenir.
   (max_attempts=3; uc gun ust uste tavan doluysa is FAILED olarak kalir ve
   panelde gorunur -- sessizce kaybolmaz.)

Kullanim:
    aksiyon-uygulayici.py           en fazla 5 onayli isi uygula
    aksiyon-uygulayici.py --durum   kapali/acik, tavanlar, bekleyen isler
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
DENETIM = KOK / "state" / "uygulayici.jsonl"
N8N_ENV = Path(os.environ.get("N8N_ENV_FILE", "/opt/lcarlie/n8n/.env"))
ISCI = "py-uygulayici"
KIRA_SN = 300
TUR_BASI_EN_FAZLA = 5
GRAPH = "https://graph.facebook.com/v21.0"
WIX = "https://www.wixapis.com"

PSQL = ["docker", "exec", "-i", "lcarlie-postgres",
        "psql", "-U", "n8n", "-d", "n8n", "-tA", "-v", "ON_ERROR_STOP=1"]


class GeciciHata(RuntimeError):
    """Ag, kota, zaman asimi: is FAILED_RETRYABLE kalir, yeniden denenir."""


class KaliciHata(RuntimeError):
    """Sozlesme ihlali ya da dogrulanamayan sonuc: is FAILED_FINAL olur."""


# --------------------------------------------------------------------------
# altyapi
# --------------------------------------------------------------------------
def _sql(sql: str) -> list[str]:
    sonuc = subprocess.run(PSQL, input=sql, capture_output=True, text=True, timeout=60)
    if sonuc.returncode != 0:
        raise GeciciHata(f"psql: {sonuc.stderr.strip()[:300]}")
    return [s for s in sonuc.stdout.split("\n") if s.strip()]


def _t(deger) -> str:
    return "'" + str(deger).replace("'", "''") + "'"


def _anahtar(ad: str) -> str:
    for satir in N8N_ENV.read_text(encoding="utf-8").splitlines():
        if satir.startswith(ad + "="):
            return satir.split("=", 1)[1].strip()
    raise KaliciHata(f"{ad} tanimli degil")


def _istek(yontem: str, url: str, basliklar: dict, govde: dict | None = None) -> dict:
    veri = json.dumps(govde).encode() if govde is not None else None
    istek = urllib.request.Request(url, data=veri, method=yontem,
                                   headers={"Content-Type": "application/json", **basliklar})
    try:
        with urllib.request.urlopen(istek, timeout=45) as yanit:
            ham = yanit.read().decode() or "{}"
            return json.loads(ham)
    except urllib.error.HTTPError as hata:
        icerik = hata.read().decode(errors="replace")[:300]
        if hata.code in (429, 500, 502, 503, 504):
            raise GeciciHata(f"HTTP {hata.code}: {icerik}") from None
        raise KaliciHata(f"HTTP {hata.code}: {icerik}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as hata:
        raise GeciciHata(f"ag: {hata}") from None


def _denetim(kayit: dict) -> None:
    DENETIM.parent.mkdir(parents=True, exist_ok=True)
    kayit["zaman"] = datetime.now(tz=timezone.utc).isoformat()
    with DENETIM.open("a", encoding="utf-8") as dosya:
        dosya.write(json.dumps(kayit, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# uygulayicilar: her biri (payload) -> ozet; yazar, GERI OKUR, dogrular
# --------------------------------------------------------------------------
def meta_kampanya(payload: dict) -> str:
    """META_CAMPAIGN_CHANGE: reklam/reklam seti/kampanya PAUSE ya da RESUME.

    PAUSE harcamayi DURDURUR (para harcatmaz). RESUME harcamayi yeniden
    baslatir; onay kapisi ve gunluk tavan bu yuzden ayni tur icinde.
    """
    nesne = str(payload.get("campaign_ref") or "")
    islem = payload.get("operation")
    if not nesne.isdigit() or islem not in ("PAUSE", "RESUME"):
        raise KaliciHata("sozlesme: campaign_ref sayisal Meta kimligi, operation PAUSE|RESUME olmali")
    hedef = "PAUSED" if islem == "PAUSE" else "ACTIVE"
    jeton = _anahtar("META_SYSTEM_TOKEN")
    once = _istek("GET", f"{GRAPH}/{nesne}?fields=name,status&access_token={jeton}", {})
    if once.get("status") == hedef:
        return f"{once.get('name', nesne)}: zaten {hedef} (degisiklik gerekmedi)"
    _istek("POST", f"{GRAPH}/{nesne}?access_token={jeton}", {}, {"status": hedef})
    sonra = _istek("GET", f"{GRAPH}/{nesne}?fields=name,status,effective_status&access_token={jeton}", {})
    if sonra.get("status") != hedef:
        raise KaliciHata(f"dogrulanamadi: yazildi ama Meta status={sonra.get('status')} diyor")
    return (f"{sonra.get('name', nesne)}: {once.get('status')} -> {sonra.get('status')} "
            f"(effective {sonra.get('effective_status')})")


def _tek_varyant(urun: dict) -> dict:
    varyantlar = (urun.get("variantsInfo") or {}).get("variants") or []
    if len(varyantlar) != 1:
        # Cok varyantli urunde (renk/boyut) hangi varyantin fiyati degisecegi
        # oneride yok; tahmin edip yanlis varyanti ezmektense reddedilir.
        raise KaliciHata(f"{len(varyantlar)} varyantli urun: tek varyantli urun destekleniyor")
    return varyantlar[0]


def _fiyat(varyant: dict) -> float | None:
    tutar = ((varyant.get("price") or {}).get("actualPrice") or {}).get("amount")
    return float(tutar) if tutar not in (None, "") else None


def fiyat_degistir(payload: dict) -> str:
    """PRICE_CHANGE: Wix urun fiyati (Catalog V3). Geri alma = eski fiyatla yeni oneri.

    🔴 SITE CATALOG V3'TE. V1 ucu 03.11'de "not supported for sites using
       Catalog V3" (501) dondu; fiyat urunde degil VARYANTTA durur ve
       guncelleme urunun revision'ini ister (eszamanli degisikligi ezmemek icin).
    """
    urun = str(payload.get("product_ref") or "")
    try:
        fiyat = round(float(payload.get("proposed_price")), 2)
    except (TypeError, ValueError):
        raise KaliciHata("sozlesme: proposed_price sayi olmali") from None
    if len(urun) != 36 or payload.get("currency") != "TRY" or not (0 < fiyat < 100000):
        raise KaliciHata("sozlesme: product_ref Wix urun kimligi, currency TRY, fiyat 0-100000")
    basliklar = {"Authorization": _anahtar("WIX_API_KEY"), "wix-site-id": _anahtar("WIX_SITE_ID")}
    adres = f"{WIX}/stores/v3/products/{urun}"
    once = _istek("GET", adres, basliklar).get("product", {})
    varyant = _tek_varyant(once)
    eski = _fiyat(varyant)
    if eski is None or not once.get("revision"):
        raise KaliciHata("urun Wix'te bulunamadi ya da fiyati/revision'i okunamadi")
    # Tek adimda %30'dan fazla oynama yazim hatasi sayilir: 1265 yerine 126,5.
    if abs(fiyat - eski) / eski > 0.30:
        raise KaliciHata(f"tek adimda %30'dan buyuk degisim ({eski} -> {fiyat}); ayri onayla bolunmeli")
    _istek("PATCH", adres, basliklar, {"product": {
        "revision": once["revision"],
        "variantsInfo": {"variants": [{
            "id": varyant["id"],
            "price": {"actualPrice": {"amount": f"{fiyat:.2f}"}},
        }]},
    }})
    sonra = _istek("GET", adres, basliklar).get("product", {})
    okunan = _fiyat(_tek_varyant(sonra))
    if okunan is None or abs(okunan - fiyat) > 0.005:
        raise KaliciHata(f"dogrulanamadi: {fiyat} yazildi, Wix {okunan} diyor")
    return f"{once.get('name', urun)}: {eski} -> {okunan} TL (Wix'ten geri okundu)"


UYGULAYICILAR = {
    "META_CAMPAIGN_CHANGE": meta_kampanya,
    "PRICE_CHANGE": fiyat_degistir,
}


# --------------------------------------------------------------------------
# dongu
# --------------------------------------------------------------------------
def acik_mi() -> bool:
    satir = _sql("SELECT config_value FROM core.ai_orchestrator_config "
                 "WHERE config_key='uygulayici_acik';")
    return bool(satir) and satir[0].strip().lower() == "true"


def kap() -> dict | None:
    turler = "ARRAY[" + ",".join(_t(t) for t in UYGULAYICILAR) + "]::text[]"
    satir = _sql("SET ROLE action_executor; SELECT row_to_json(x) FROM "
                 f"core.ai_claim_approved_action_tipli({_t(ISCI)}, {KIRA_SN}, {turler}) x;")
    satir = [s for s in satir if s.startswith("{")]
    return json.loads(satir[0]) if satir else None


def bitir(is_: dict, sinif: str, ozet: str) -> None:
    _sql("SET ROLE action_executor; SELECT core.ai_complete_action_execution("
         f"{int(is_['execution_id'])}, {_t(is_['lease_token'])}::uuid, {_t(sinif)}, {_t(ozet[:990])});")


def tavan(is_: dict) -> str | None:
    tutar = (is_.get("payload") or {}).get("tutar") or 0
    satir = _sql("SET ROLE action_executor; SELECT COALESCE(core.ai_action_tavan_dolu("
                 f"{_t(is_['action_type'])}, {float(tutar)}), '');")
    satir = [s for s in satir if s.strip() and s.strip() != "SET"]
    return satir[0] if satir and satir[0].strip() else None


def uygula(is_: dict) -> str:
    tur = is_["action_type"]
    dolu = tavan(is_)
    if dolu:
        bitir(is_, "FAILED_RETRYABLE", f"tavan: {dolu}")
        return "TAVAN"
    try:
        ozet = UYGULAYICILAR[tur](is_.get("payload") or {})
        sinif = "EXECUTED"
    except GeciciHata as hata:
        ozet, sinif = f"gecici: {hata}", "FAILED_RETRYABLE"
    except KaliciHata as hata:
        ozet, sinif = f"kalici: {hata}", "FAILED_FINAL"
    except Exception as hata:  # noqa: BLE001 - bilinmeyen hata isi YAKMAZ, tekrar denenir
        ozet, sinif = f"beklenmeyen {type(hata).__name__}: {str(hata)[:200]}", "FAILED_RETRYABLE"
    bitir(is_, sinif, ozet)
    _denetim({"execution_id": is_["execution_id"], "action_id": is_["action_id"],
              "tur": tur, "sonuc": sinif, "ozet": ozet})
    print(f"#{is_['action_id']} {tur}: {sinif} - {ozet}")
    return sinif


def durum() -> None:
    print("uygulayici:", "ACIK" if acik_mi() else "KAPALI (acil durdurma)")
    print("tanidigi turler:", ", ".join(UYGULAYICILAR))
    for s in _sql("SELECT action_type||' | '||execution_enabled FROM core.ai_action_type ORDER BY 1;"):
        print("  tur | uygulama acik:", s)
    for s in _sql("SELECT action_type||' | '||gunluk_adet||' adet | '||COALESCE(gunluk_tutar::text,'-')"
                  "||' TL' FROM core.ai_action_tavan ORDER BY 1;"):
        print("  tavan:", s)


def main() -> int:
    if "--durum" in sys.argv:
        durum()
        return 0
    if not acik_mi():
        print("uygulayici KAPALI (core.ai_orchestrator_config.uygulayici_acik)")
        return 0
    sayac = 0
    while sayac < TUR_BASI_EN_FAZLA:
        is_ = kap()
        if not is_:
            break
        uygula(is_)
        sayac += 1
        time.sleep(1)
    if sayac == 0:
        print("onayli bekleyen is yok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
