"""Places API (New) ile Ankara lead kesfi -- OSM'in yetmedigi 16 hedef.

NEDEN PLACES
OSM olculdu ve yalniz eczanede ise yariyor (1752 kayit, %79 telefonlu).
Digerlerinde hem kayit az hem telefon yok:
    klinik 198/%8 · spor salonu 146/%10 · guzellik 108/%12 · muayenehane 20/%20
Ankara'da 20 muayenehane olamaz; OSM'de yoklar. Places onlari biliyor.

HEDEF SIRASI SATIS MANTIGINA GORE -- "kim onerir" degil "kim SATIN ALIR"
Doktor satin almaz, ONERIR. Ciro satin alandan gelir:
    toplu alan   bakim evi, huzurevi, evde bakim      -> tuketilir, tekrarlar
    alip satan   eczane, kozmetik magazasi            -> dogrudan ciro
    kullanip satan  guzellik merkezi, spa, kuafor     -> demo etkisi
    yalniz oneren   doktor, muayenehane               -> dolayli, yuksek guven
Doktor kanali birakilmiyor ama BIRINCI SIRADA degil.

MALIYET KAPISI -- sert
Places Pro SKU 32 USD/1000, ucretsiz kota ayda 5.000 (devretmez).
Bu betik VARSAYILAN olarak ucretsiz kotanin altinda kalir ve tavani asarsa
DURUR. Tavani asmak icin --tavan verilmeli: kazayla fatura uretmek yok.

ALAN MASKESI -- SKU'yu belirleyen sey
displayName + formattedAddress  = Essentials (ucuz)
+ nationalPhoneNumber, websiteUri = Enterprise (35 USD/1000, ucretsiz 1.000/ay)
Telefon olmadan lead lead degil, o yuzden Enterprise kullanilir; tavan da
buna gore konur.

SARTLAR
Places verisi KALICI SAKLANAMAZ. core.lead'de kaynak='places' ile isaretlenir
ve saklama_sonu kisa tutulur; core.lead_saklama_temizligi() siler.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

UC = "https://places.googleapis.com/v1/places:searchText"
MASKE = ("places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
         "places.websiteUri,places.location,places.id,places.primaryType")
IL = "Ankara"
PLACES_SAKLAMA_GUN = 30      # Google onbellek sartlari -- kisa tutulur

# (hedef, arama sorgusu, oncelik)  oncelik 1 = en yuksek beklenen ciro
HEDEFLER = [
    # KURUMSAL KUME -- toplu alir, tuketir, tekrarlar. Beklenen ciro en yuksek.
    ("bakim evi",            "Ankara huzurevi bakım evi", 1),
    ("evde bakim",           "Ankara evde bakım hizmeti", 1),
    # Diyaliz: hasta haftada 3 kez, 4+ saat sabit pozisyonda. DERMABED'in
    # ("uzun sureli yatis, surtunme veya basinca bagli hassaslasan cilt")
    # tarif ettigi kullanim baglami. Kurumsal, duzenli, tekrarlayan temas.
    # 🔴 Bu bir KANAL degerlendirmesidir, tibbi iddia DEGILDIR -- musteriye
    # giden metinde hastalik veya tedavi baglantisi kurulamaz.
    ("diyaliz merkezi",      "Ankara diyaliz merkezi", 1),
    ("guzellik merkezi",     "Ankara güzellik merkezi", 3),
    ("epilasyon",            "Ankara lazer epilasyon merkezi", 3),
    ("spa masaj",            "Ankara spa masaj salonu", 4),
    ("kuafor",               "Ankara kuaför", 5),
    ("spor salonu",          "Ankara spor salonu fitness", 6),
    ("pediatri",             "Ankara çocuk doktoru muayenehane", 7),
    ("dermatoloji",          "Ankara dermatoloji cildiye muayenehane", 8),
    ("kadin dogum",          "Ankara kadın doğum uzmanı muayenehane", 9),
    ("estetik cerrahi",      "Ankara estetik plastik cerrahi kliniği", 10),
    ("fizik tedavi",         "Ankara fizik tedavi ve rehabilitasyon", 11),
    ("dis hekimi",           "Ankara diş hekimi kliniği", 12),
    ("podoloji",             "Ankara podoloji ayak sağlığı merkezi", 13),
    ("uroloji",              "Ankara üroloji muayenehane", 14),
    ("goz hastaliklari",     "Ankara göz hastalıkları muayenehane", 15),
    ("kozmetik magazasi",    "Ankara kozmetik mağazası parfümeri", 16),
    ("medikal malzeme",      "Ankara medikal malzeme satış", 17),
]


def anahtar() -> str:
    for ad in ("PLACES_API_KEY", "GOOGLE_MAPS_API_KEY"):
        v = (os.environ.get(ad) or "").strip()
        if v:
            return v
    return ""


def ara(ak: str, sorgu: str, sayfa: str | None = None):
    govde = {"textQuery": sorgu, "languageCode": "tr", "regionCode": "TR",
             "maxResultCount": 20}
    if sayfa:
        govde["pageToken"] = sayfa
    istek = urllib.request.Request(UC, data=json.dumps(govde).encode(), headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": ak,
        "X-Goog-FieldMask": MASKE + ",nextPageToken",
    })
    with urllib.request.urlopen(istek, timeout=40) as y:
        return json.load(y)


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-v", "ON_ERROR_STOP=1"],
        input=sql, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:400])
    return r.stdout


def q(v) -> str:
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tavan", type=int, default=900,
                    help="en fazla API cagrisi (varsayilan 900 -- ucretsiz kotanin altinda)")
    ap.add_argument("--hedef", default="", help="yalniz bu hedef")
    ap.add_argument("--kuru", action="store_true", help="yaz ama veritabanina DOKUNMA")
    a = ap.parse_args()

    ak = anahtar()
    if not ak:
        print("PLACES_API_KEY yok. Google Cloud konsolundan:")
        print("  1) Places API (New) -> Enable")
        print("  2) Credentials -> API key (kisitlama: yalniz Places API New)")
        print("  3) anahtari /etc/lcarlie/jarvis-web.env icine PLACES_API_KEY= olarak ekle")
        return 2

    bitis = date.today() + timedelta(days=PLACES_SAKLAMA_GUN)
    cagri = 0
    toplam, telefonlu = 0, 0
    print("  tavan: %d cagri   saklama: %d gun (Places sartlari)" % (a.tavan, PLACES_SAKLAMA_GUN))
    print()
    for hedef, sorgu, _oncelik in HEDEFLER:
        if a.hedef and a.hedef != hedef:
            continue
        sayfa, bulunan, h_tel = None, 0, 0
        while True:
            if cagri >= a.tavan:
                print("  TAVANA ULASILDI (%d cagri) -- duruluyor" % cagri)
                break
            try:
                d = ara(ak, sorgu, sayfa)
                cagri += 1
            except urllib.error.HTTPError as e:
                govde = e.read().decode("utf8", "ignore")
                try:
                    m = json.loads(govde)["error"]["message"]
                except Exception:                                 # noqa: BLE001
                    m = govde[:140]
                print("  %-20s %s -- %s" % (hedef, e.code, m.replace(ak, "<ANAHTAR>")[:110]))
                break
            except Exception as e:                                # noqa: BLE001
                print("  %-20s HATA -- %s" % (hedef, str(e).replace(ak, "<ANAHTAR>")[:90]))
                break

            satir = []
            for p in d.get("places", []):
                ad = (p.get("displayName") or {}).get("text", "").strip()
                if len(ad) < 2:
                    continue
                tel = p.get("nationalPhoneNumber")
                konum = p.get("location") or {}
                satir.append((
                    "places", "places:" + str(p.get("id")), hedef, IL, None, ad,
                    tel, p.get("websiteUri"), p.get("formattedAddress"),
                    konum.get("latitude"), konum.get("longitude"), bitis.isoformat()))
                bulunan += 1
                if tel:
                    h_tel += 1
            if satir and not a.kuru:
                deger = ",".join(
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::date)" % (
                        q(x[0]), q(x[1]), q(x[2]), q(x[3]), q(x[4]), q(x[5]), q(x[6]),
                        q(x[7]), q(x[8]),
                        x[9] if x[9] is not None else "NULL",
                        x[10] if x[10] is not None else "NULL", q(x[11]))
                    for x in satir)
                psql("INSERT INTO core.lead (kaynak,kaynak_kimlik,segment,il,ilce,ad,"
                     "telefon,site,adres,enlem,boylam,saklama_sonu) VALUES " + deger +
                     " ON CONFLICT (kaynak,kaynak_kimlik) DO UPDATE SET "
                     "ad=EXCLUDED.ad, telefon=EXCLUDED.telefon, site=EXCLUDED.site, "
                     "adres=EXCLUDED.adres, toplandi=now(), "
                     "saklama_sonu=EXCLUDED.saklama_sonu;")
            sayfa = d.get("nextPageToken")
            if not sayfa:
                break
            time.sleep(2)

        toplam += bulunan
        telefonlu += h_tel
        print("  %-20s %4d kayit   %4d telefonlu   (%d cagri)" % (hedef, bulunan, h_tel, cagri))
        if cagri >= a.tavan:
            break
        time.sleep(1)

    print()
    print("  TOPLAM  %d kayit, %d telefonlu, %d API cagrisi" % (toplam, telefonlu, cagri))
    if not a.kuru:
        print()
        print(psql("SELECT segment, kaynak, kayit, telefonlu FROM mart.lead_ozet "
                   "WHERE il = 'Ankara' ORDER BY kayit DESC;"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
