"""Görsel onayları (sahip isteği 05.11.2026): üretilen görseller tek tek gösterilir,
sahip sağa (beğendi) / sola (beğenmedi + neden) kaydırır. Kararlar core.gorsel_onay'da
kalıcıdır; jarvis/gorsel_tercih.py beğenilmeme nedenlerini yeni istemlere ekler.

Yalnız Jarvis'in ÜRETTİĞİ görseller sorulur: tarayıcı (ChatGPT) çıktıları, kreatif
parti kareleri ve Instagram için ChatGPT'de üretilen gönderi görselleri. Ekran
görüntüleri, etiket kontrol kırpıntıları ve Pillow kompozitleri sorulmaz.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from personal_action_store import _connect

NEDENLER = ("Ürün yanlış ya da bozuk", "Logo veya yazı hatalı", "Yapay / plastik görünüyor",
            "Renk ve ışık kötü", "Kadraj ve kompozisyon kötü", "Marka tarzına uymuyor",
            "İddia / mevzuat riski")
IG_DIR = Path(os.environ.get("GONDERI_GORSEL_DIR", "/opt/lcarlie/gonderi-gorsel"))
# Görsel izleri (benzerlik özeti) burada saklanır: her açılışta 70 görseli yeniden okumamak için.
IZ_DOSYA = Path(os.environ.get("GORSEL_ONAY_IZ", "/opt/lcarlie/jarvis-phase2/state/gorsel-onay-iz.json"))
# 16x16 gri özetin en fazla bu kadar biti farklıysa aynı görsel sayılır. Ölçüldü 05.11.2026:
# aynı görselin PNG ve JPG kopyası ≤20 bit, farklı kompozisyonlar 60+ bit farklı.
BENZERLIK_ESIGI = 20
GORSEL = (".png", ".jpg", ".jpeg", ".webp")


class OnayHatasi(ValueError):
    pass


def _adaylar(tarayici_dir: Path, kreatif_dir: Path) -> dict[str, dict]:
    """anahtar → görsel bilgisi. Anahtar, panelin servis ettiği yolun kendisidir."""
    adaylar: dict[str, tuple[float, dict]] = {}
    if tarayici_dir.is_dir():
        for yol in tarayici_dir.glob("tarayici-*.json"):
            try:
                kayit = json.loads(yol.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            slug = str(kayit.get("slug") or yol.stem)
            if not re.fullmatch(r"tarayici-\d+", slug) or kayit.get("hedef") != "chatgpt_image":
                continue
            for ad in kayit.get("dosyalar") or []:
                ad = str(ad)
                dosya = tarayici_dir / f"{slug}-dosyalar" / ad
                if ad.startswith(("ekran-", "EKSIK:", ".")) or "/" in ad or not ad.lower().endswith(GORSEL) or not dosya.is_file():
                    continue
                anahtar = f"tarayici/{slug}-dosyalar/{ad}"
                adaylar[anahtar] = (dosya.stat().st_mtime, {
                    "kaynak": "tarayici", "_yol": dosya, "url": f"/tarayici/{slug}-dosyalar/{quote(ad)}",
                    "baslik": f"ChatGPT görseli · iş #{kayit.get('is_id')}",
                    "aciklama": str(kayit.get("istem") or "")[:400]})
    if kreatif_dir.is_dir():
        for dosya in kreatif_dir.glob("*-gorseller/*"):
            if not dosya.is_file() or not dosya.name.lower().endswith(GORSEL):
                continue
            parti = dosya.parent.name[:-len("-gorseller")]
            anahtar = f"kreatif/{dosya.parent.name}/{dosya.name}"
            adaylar[anahtar] = (dosya.stat().st_mtime, {
                "kaynak": "kreatif", "_yol": dosya, "url": f"/kreatif/{quote(dosya.parent.name)}/{quote(dosya.name)}",
                "baslik": f"Kreatif · {parti.split('-')[0].upper()}", "aciklama": parti})
    if IG_DIR.is_dir():
        for dosya in IG_DIR.glob("jarvis-gpt-web-*"):
            if dosya.is_file() and dosya.name.lower().endswith(GORSEL):
                urun = dosya.stem[len("jarvis-gpt-web-"):].rsplit("-", 1)[0]
                adaylar[f"gonderi-gorsel/{dosya.name}"] = (dosya.stat().st_mtime, {
                    "kaynak": "ig", "_yol": dosya, "url": f"/gonderi-gorsel/{quote(dosya.name)}",
                    "baslik": f"Instagram · {urun.replace('-', ' ').upper()}", "aciklama": ""})
    sirali = sorted(adaylar.items(), key=lambda kv: kv[1][0], reverse=True)
    return {anahtar: dict(bilgi, anahtar=anahtar) for anahtar, (_t, bilgi) in sirali}


def _iz(yol: Path, onbellek: dict) -> str | None:
    """16x16 gri ortalama özeti (aHash). Dosya değişmedikçe önbellekten gelir."""
    anahtar = "%s|%d|%d" % (yol, yol.stat().st_mtime_ns, yol.stat().st_size)
    if anahtar not in onbellek:
        try:
            from PIL import Image
            with Image.open(yol) as img:
                pikseller = list(img.convert("L").resize((16, 16)).getdata())
        except Exception:  # noqa: BLE001 - okunamayan görsel tekil sayılır
            return None
        ort = sum(pikseller) / len(pikseller)
        onbellek[anahtar] = "".join("1" if p > ort else "0" for p in pikseller)
    return onbellek[anahtar]


def _gruplar(adaylar: dict[str, dict]) -> list[list[str]]:
    """Aynı ya da neredeyse aynı görselleri tek grupta toplar (05.11.2026: 71 görselin
    24'ü tekrardı: tarayıcı işçisi eski görselleri yeniden indiriyor, kreatif hat da
    aynı görseli JPG olarak bir daha kaydediyor). Grup içinde kreatif kopya öne alınır."""
    try:
        onbellek = json.loads(IZ_DOSYA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        onbellek = {}
    izler = {k: _iz(a["_yol"], onbellek) for k, a in adaylar.items()}
    try:
        IZ_DOSYA.parent.mkdir(parents=True, exist_ok=True)
        gecici = IZ_DOSYA.with_suffix(".yaziliyor")
        gecici.write_text(json.dumps(onbellek), encoding="utf-8")
        gecici.replace(IZ_DOSYA)
    except OSError:
        pass  # önbellek yazılamazsa yalnız yavaşlar
    gruplar: list[list[str]] = []
    for k in adaylar:
        for grup in gruplar:
            a, b = izler[k], izler[grup[0]]
            if a and b and sum(x != y for x, y in zip(a, b, strict=True)) <= BENZERLIK_ESIGI:
                grup.append(k)
                break
        else:
            gruplar.append([k])
    oncelik = {"kreatif": 0, "ig": 1, "tarayici": 2}
    return [sorted(g, key=lambda k: oncelik.get(adaylar[k]["kaynak"], 9)) for g in gruplar]


def _disa(aday: dict, grup: list[str]) -> dict:
    return {k: v for k, v in aday.items() if not k.startswith("_")} | {"kopya": len(grup) - 1}


def durum(owner: str, tarayici_dir: Path, kreatif_dir: Path) -> dict:
    adaylar = _adaylar(tarayici_dir, kreatif_dir)
    gruplar = _gruplar(adaylar)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT anahtar FROM core.gorsel_onay")
        verilen = {r["anahtar"] for r in cur.fetchall()}
        cur.execute("SELECT karar, count(*) AS adet FROM core.gorsel_onay WHERE yorum NOT LIKE 'kopya:%' GROUP BY karar")
        sayilar = {r["karar"]: int(r["adet"]) for r in cur.fetchall()}
        cur.execute("""SELECT n AS metin, count(*) AS adet FROM core.gorsel_onay, unnest(nedenler) n
            WHERE karar = 'BEGENMEDI' GROUP BY n ORDER BY count(*) DESC, n LIMIT 10""")
        nedenler = [dict(r, adet=int(r["adet"])) for r in cur.fetchall()]
        cur.execute("""SELECT yorum, baslik, to_char(karar_zamani AT TIME ZONE 'Europe/Istanbul', 'DD.MM.YYYY HH24:MI') AS zaman
            FROM core.gorsel_onay WHERE karar = 'BEGENMEDI' AND length(btrim(yorum)) >= 3 AND yorum NOT LIKE 'kopya:%'
            ORDER BY karar_zamani DESC LIMIT 8""")
        yorumlar = [dict(r) for r in cur.fetchall()]
    # Bir kopyasına karar verilmiş görsel bir daha sorulmaz.
    kuyruk = [_disa(adaylar[g[0]], g) for g in gruplar if not verilen.intersection(g)]
    return {"kuyruk": kuyruk[:80], "bekleyen": len(kuyruk), "neden_secenekleri": list(NEDENLER),
            "ozet": {"begendi": sayilar.get("BEGENDI", 0), "begenmedi": sayilar.get("BEGENMEDI", 0),
                     "nedenler": nedenler, "yorumlar": yorumlar}}


def karar_ver(owner: str, body: dict, tarayici_dir: Path, kreatif_dir: Path) -> dict:
    if not isinstance(body, dict):
        raise OnayHatasi("Karar geçersiz.")
    anahtar = str(body.get("anahtar") or "")
    adaylar = _adaylar(tarayici_dir, kreatif_dir)
    aday = adaylar.get(anahtar)
    if aday is None:
        raise OnayHatasi("Görsel bulunamadı ya da onaya açık değil.")
    karar = body.get("karar")
    if karar not in ("BEGENDI", "BEGENMEDI"):
        raise OnayHatasi("Karar beğendim ya da beğenmedim olmalı.")
    nedenler = body.get("nedenler") or []
    if not isinstance(nedenler, list) or any(n not in NEDENLER for n in nedenler):
        raise OnayHatasi("Neden listeden seçilmeli.")
    yorum = " ".join(str(body.get("yorum") or "").split())[:1000]
    if karar == "BEGENMEDI" and not nedenler and len(yorum) < 3:
        raise OnayHatasi("Neden beğenmediğini seç ya da kısaca yaz; Jarvis bundan öğrenecek.")
    if karar == "BEGENDI":
        nedenler = []
    grup = next((g for g in _gruplar(adaylar) if anahtar in g), [anahtar])
    with _connect() as conn, conn.cursor() as cur:
        # Karar görselin bütün kopyalarına yazılır; nedenler istatistiği şişmesin diye
        # yalnız gösterilen kopya nedenleri taşır, diğerleri "kopya" olarak işaretlenir.
        for k in grup:
            asil = k == anahtar
            cur.execute("""INSERT INTO core.gorsel_onay (kaynak, anahtar, baslik, karar, nedenler, yorum, karar_veren)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (anahtar) DO UPDATE SET karar = EXCLUDED.karar, nedenler = EXCLUDED.nedenler,
                  yorum = EXCLUDED.yorum, karar_veren = EXCLUDED.karar_veren, karar_zamani = clock_timestamp()""",
                        (adaylar[k]["kaynak"], k, adaylar[k]["baslik"],
                         karar, nedenler if asil else [], yorum if asil else ("kopya: " + anahtar)[:1000], owner))
    return {"anahtar": anahtar, "karar": karar, "kopya": len(grup) - 1}
