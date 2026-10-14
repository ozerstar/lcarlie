"""ÜRÜN GÖRSEL HATTI: Wix'ten indir → arka planı kes → Canva'ya yükle.

Sahip 22.09.2026: *"tüm ürünlerin arka plansız görselleri oluşturulsun...
Bu dosyalar elimizde hazır olsun, uğraşmayalım arka plan silmekle."*

🔴 CANVA BUNU YAPAMIYOR. Canva'nın arka plan silicisi ARAYÜZ özelliği;
Connect API'de böyle bir uç yok (61 ucun tamamı tarandı). Hesabın
`export_png_transparency` yetkinliği var ama o, ŞEFFAF ÖĞE İÇEREN BİR
TASARIMI şeffaf PNG olarak dışa aktarmak demek -- fotoğraftan arka plan
silmek değil. O yüzden kesim yerelde rembg ile yapılıyor, sonuç Canva'ya
VARLIK olarak yükleniyor: şablonlar oradan kullanacak.

🔴 KESİM DOĞRULANIYOR, KÖRLEMESİNE KABUL EDİLMİYOR. rembg bazen ürünün
bir kısmını da siler. Üç ölçüt bakılıyor:
    - şeffaf olmayan piksel oranı %2'den az   -> ürünü yemiş
    - şeffaf olmayan piksel oranı %95'ten çok -> hiçbir şey silmemiş
    - en büyük bağlı bileşen dışında parça    -> kırpıntı kalmış
Şüpheli olan "İNCELE" işaretiyle ayrılıyor; sessizce iyi sayılmıyor.

🔴 ADLANDIRMA ÜRÜN KİMLİĞİNE BAĞLI. Dosya adı ürün adından türetilirse
Türkçe karakter ve boşluk yüzünden eşleşme kopar (bu tuzağa daha önce
düşüldü). SKU varsa o, yoksa Wix ürün kimliği kullanılıyor.
"""
import json
import re
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")

HEDEF = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun")
HAM = HEDEF / "ham"
KESIM = HEDEF / "kesim"
for d in (HAM, KESIM):
    d.mkdir(parents=True, exist_ok=True)


def duz_ad(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("ı", "i")
                              .replace("ğ", "g").replace("ş", "s")
                              .replace("ö", "o").replace("ü", "u")
                              .replace("ç", "c").replace("İ", "i"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()[:48]


def urunler() -> list[dict]:
    sql = ("SELECT json_agg(t) FROM (SELECT ham->>'id' AS id, "
           "ham->>'name' AS ad, ham->>'sku' AS sku, ham->'media' AS medya "
           "FROM raw.wix_urun) t;")
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=60, check=False)
    if r.returncode:
        raise SystemExit("ürün listesi okunamadı: " + (r.stderr or "")[:200])
    return json.loads(r.stdout.strip() or "[]")


def ana_gorsel(medya) -> str | None:
    """Wix medya yapısından ANA görselin tam boy adresini çıkarır."""
    if not medya:
        return None
    m = medya if isinstance(medya, dict) else {}
    aday = m.get("mainMedia") or {}
    img = (aday.get("image") or {})
    url = img.get("url")
    if url:
        return url
    for it in (m.get("items") or []):
        u = ((it.get("image") or {}).get("url"))
        if u:
            return u
    return None


def indir(url: str, yol: Path) -> bool:
    if yol.exists() and yol.stat().st_size > 10_000:
        return True
    try:
        istek = urllib.request.Request(
            url, headers={"User-Agent": "lcarlie-jarvis/1.0"})
        with urllib.request.urlopen(istek, timeout=60) as c:
            veri = c.read()
        if len(veri) < 5_000:
            return False
        yol.write_bytes(veri)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"      indirilemedi: {str(e)[:70]}")
        return False


def main():
    liste = urunler()
    print(f"{len(liste)} ürün okundu\n")
    sayac = {"indi": 0, "adres_yok": 0, "hata": 0}
    kayit = []
    for u in liste:
        ad = duz_ad(u.get("sku") or u.get("ad") or u.get("id"))
        url = ana_gorsel(u.get("medya"))
        if not url:
            sayac["adres_yok"] += 1
            print(f"  ⛔ {u.get('ad','?')[:38]:<40} görsel adresi yok")
            continue
        hedef = HAM / f"{ad}.jpg"
        if indir(url, hedef):
            sayac["indi"] += 1
            kb = hedef.stat().st_size // 1024
            print(f"  ✅ {u.get('ad','?')[:38]:<40} {ad}.jpg ({kb} KB)")
            kayit.append({"id": u.get("id"), "ad": u.get("ad"),
                          "sku": u.get("sku"), "dosya": f"{ad}.jpg",
                          "kaynak": url})
        else:
            sayac["hata"] += 1

    (HEDEF / "kunye.json").write_text(
        json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nindi={sayac['indi']}  adres_yok={sayac['adres_yok']}  "
          f"hata={sayac['hata']}")
    print(f"künye: {HEDEF / 'kunye.json'}")


if __name__ == "__main__":
    main()
