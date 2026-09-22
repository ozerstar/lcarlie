#!/usr/bin/env python3
"""TASARIM GÖREVİ — panelin bir parçasını EKİBE tasarlattırır.

Sahip 21.09.2026: *"bu görsel düzeltmeyi bizim kreatif ekibine görev
olarak ver ve bu panelin nasıl olması gerektiğini ilk önce onlar
düşünsün, red team çürütsün, müdür karar versin ve en iyi halini
uygulayalım — böylelikle sistemin düzgün çalıştığını da görmüş oluruz."*

Zincir, kreatif hattının aynısı ama konusu ÜRÜN değil ARAYÜZ:
  1. ÖLÇÜM        sorunun sayısal hâli (koddan okunur, uydurulmaz)
  2. EKİP         üç kreatif rol ayrı ayrı öneri verir
  3. RED TEAM     her öneriyi çürütmeye çalışır
  4. DİREKTÖR     birini seçer ve GEREKÇESİNİ yazar
  5. ÇIKTI        uygulanabilir tasarım şartnamesi + onay kuyruğu görevi

🔴 ÖNERİ "GÜZEL OLSUN" DİYEMEZ. Her öneri UYGULANABİLİR olmak zorunda:
hangi CSS kuralı, hangi sınıf, hangi ölçü. Uygulanamayan bir tasarım
görüşü, panele bakıp "daha iyi olmalı" demekten farksızdır.

Çıkış: 0=karar verildi · 1=hata · 2=model cevap vermedi
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis.memory import CompanyMemory  # noqa: E402
from jarvis.model_layer import ModelRouter  # noqa: E402

CIKTI = Path(os.environ.get("TASARIM_DIR", str(KOK / "state" / "tasarim")))

ROLLER = (
    ("ART", "Sanat Yönetmeni", """Kompozisyon ve hiyerarşi gözüyle bak.
Hangi öğe ne kadar yer kaplamalı, göz önce nereye gitmeli, boşluk nerede
olmalı. Ölçü ver: yüzde, rem, satır sayısı."""),
    ("CREATIVE_STRAT", "Kreatif Direktör", """Kullanım gözüyle bak.
Bu ekranda insan NE YAPMAYA çalışıyor, hangi bilgi onu o işe götürür,
hangisi yolundan alıkoyar. Gereksizi SİLMEYİ öner."""),
    ("BRAND", "Marka Stratejisti", """Marka gözüyle bak. L'CARLIÉ koyu,
sakin, şampanya altını bir kimlik; panel bir kontrol odası. Önerin bu
kimliği güçlendirsin, bozmasın."""),
)

SISTEM = """Sen L'CARLIÉ'nin arayüz tasarım ekibindesin. Türkçe yazarsın.

🔴 ÖNERİN UYGULANABİLİR OLMAK ZORUNDA. "Daha ferah olsun", "modern
dursun" gibi cümleler KABUL EDİLMEZ. Her öneri şunu söyler: hangi öğe,
hangi ölçü, hangi davranış. Örnek kabul edilir biçim:
  "cevap kutusu en fazla 12 satır göstersin, gerisi 'devamını gör' ile
   açılsın; yükseklik 60vh'yi geçmesin"

🔴 SANA VERİLEN ÖLÇÜMLER GERÇEKTİR, DEĞİŞTİRME. Ekranda olmayan bir
şeyi varmış gibi anlatma.

SADECE geçerli JSON döndür."""

ISTEK = """SORUN
{sorun}

ÖLÇÜLEN DURUM
{olcum}

SENİN ROLÜN — {rol}
{rubrik}

JSON şeması, birebir:
{{"oneri_adi": "kısa ad",
  "ne_degisecek": ["uygulanabilir madde; her biri ölçü içersin"],
  "neden": "tek paragraf gerekçe",
  "riski": "bu değişiklik neyi kötüleştirebilir"}}"""

RED_SISTEM = """Sen bu tasarım önerilerini ÇÜRÜTMEKLE görevlisin. Türkçe.

Her itirazın: NEYE (birebir alıntı) · NEDEN yanlış · NE YAPILSIN.
"Beğenmedim" bir itiraz değildir.

Özellikle şunlara bak: öneri bilgi SAKLIYOR mu (kullanıcı görmesi
gerekeni kaybeder mi), mobilde çalışır mı, uygulanabilir mi.

SADECE geçerli JSON döndür."""

RED_ISTEK = """Şu {adet} tasarım önerisini çürüt:

{oneriler}

JSON: {{"itirazlar": [{{"oneri": "hangi öneri", "alinti": "birebir",
 "itiraz": "neden yanlış", "duzeltme": "ne yapılsın",
 "agirlik": "YÜKSEK|ORTA|DÜŞÜK"}}]}}"""

MUDUR_SISTEM = """Sen tasarım direktörüsün. Türkçe. Bir öneriyi SEÇER ve
gerekçesini yazarsın. Seçtiğin öneriyi red team itirazlarına göre
DÜZELTEBİLİRSİN; o zaman neyi değiştirdiğini söyle.

🔴 "Hepsi güzel" diyemezsin. Tek bir uygulanacak şartname çıkar.

SADECE geçerli JSON döndür."""

MUDUR_ISTEK = """ÖNERİLER
{oneriler}

RED TEAM İTİRAZLARI
{itirazlar}

JSON: {{"secilen": "öneri adı",
 "gerekce": "neden bu",
 "red_teamden_alinan": ["itirazlardan kabul edilenler"],
 "uygulanacak": ["kesinleşmiş, uygulanabilir maddeler; ölçülü"],
 "uygulanmayacak": ["reddedilen öneriler ve NEDEN"]}}"""


def _json_cek(metin: str):
    metin = (metin or "").strip()
    if metin.startswith("```"):
        p = metin.split("```")
        if len(p) > 1:
            metin = p[1].removeprefix("json").strip()
    bas, son = metin.find("{"), metin.rfind("}")
    if bas < 0 or son <= bas:
        return None
    try:
        return json.loads(metin[bas:son + 1])
    except json.JSONDecodeError:
        return None


def _uret(r: ModelRouter, sistem: str, istek: str, azami: int = 2200):
    sonuc, _t, _c = r.generate(
        [{"role": "system", "content": sistem},
         {"role": "user", "content": istek}], azami,
        # 🔴 Burada `escalate` YOKTU ama kayit defteri bu isi muhakeme
        # kademesine koyuyor: sartname uretiyor ve kirmizi takim denetliyor.
        is_anahtari="tasarim_gorevi")
    ham = sonuc.get("text") or ""
    veri = _json_cek(ham)
    if veri is None:
        print(f"    JSON çıkmadı · cevap {len(ham)} kr · {ham[:120]!r}",
              file=sys.stderr)
    return veri


def main() -> int:
    ap = argparse.ArgumentParser(description="Paneli ekibe tasarlattırır")
    ap.add_argument("--sorun", required=True)
    ap.add_argument("--olcum", required=True,
                    help="sorunun sayısal hâli; UYDURULMAZ, ölçülür")
    ap.add_argument("--ad", default="panel")
    a = ap.parse_args()

    r = ModelRouter()
    print(f"TASARIM GÖREVİ · {a.ad}")
    print(f"  sorun: {a.sorun[:90]}")

    oneriler = []
    for kod, rol, rubrik in ROLLER:
        o = _uret(r, SISTEM, ISTEK.format(sorun=a.sorun, olcum=a.olcum,
                                          rol=rol, rubrik=rubrik))
        if not isinstance(o, dict):
            print(f"  {rol}: öneri üretemedi", file=sys.stderr)
            continue
        o["rol"], o["departman"] = rol, kod
        oneriler.append(o)
        print(f"  {rol}: “{o.get('oneri_adi')}” · "
              f"{len(o.get('ne_degisecek') or [])} madde")
    if not oneriler:
        return 2

    red = _uret(r, RED_SISTEM, RED_ISTEK.format(
        adet=len(oneriler), oneriler=json.dumps(oneriler, ensure_ascii=False)))
    itirazlar = (red or {}).get("itirazlar") or []
    print(f"  RED TEAM: {len(itirazlar)} itiraz")

    karar = _uret(r, MUDUR_SISTEM, MUDUR_ISTEK.format(
        oneriler=json.dumps(oneriler, ensure_ascii=False),
        itirazlar=json.dumps(itirazlar, ensure_ascii=False)), 2600)
    if not isinstance(karar, dict):
        print("  DİREKTÖR karar veremedi", file=sys.stderr)
        return 2
    print(f"  DİREKTÖR: “{karar.get('secilen')}” · "
          f"{len(karar.get('uygulanacak') or [])} madde uygulanacak")

    CIKTI.mkdir(parents=True, exist_ok=True)
    damga = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    ad = re.sub(r"[^a-z0-9]+", "-", a.ad.casefold()).strip("-")
    yol = CIKTI / f"{ad}-{damga}.json"
    yol.write_text(json.dumps({
        "ad": a.ad, "sorun": a.sorun, "olcum": a.olcum,
        "uretildi": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "oneriler": oneriler, "red_team": itirazlar, "karar": karar,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

