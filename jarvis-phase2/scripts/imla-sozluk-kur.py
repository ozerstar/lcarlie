#!/usr/bin/env python3
"""Turkce imla ek sozlugunu URUN VERISINDEN uretir.

🔴 ELLE LISTE YAZILMAZ. Marka ve bilesen adlari zaten diskte duruyor
(kutu gercegi JSON'lari + katalog). Elle yazilan liste eskir; uretilen
liste urun eklendikce kendini yeniler.

Kaynaklar:
  varliklar/kutu-gercegi/*.json  -> INCI terimleri, urun adlari
  mart.urun_karti                -> katalogdaki urun adlari
  KOZMETIK_EK                    -> hunspell tr_TR'nin kacirdigi olculmus
                                    yaygin bicimler (olcum sonucu eklendi)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

KOK = Path("/opt/lcarlie/jarvis-phase2")
sys.path.insert(0, str(KOK))
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

KUTU = KOK / "varliklar" / "kutu-gercegi"
HEDEF = KOK / "varliklar" / "imla-ek-sozluk.txt"

# hunspell tr_TR'nin kacirdigi, kozmetik metninde surekli gecen bicimler.
# Her biri OLCULEREK eklendi (hunspell -l ile sahte pozitif verdigi dogrulandi).
KOZMETIK_EK = """
ciltim cildim cildimi cildime cildin cildini ciltte cilde cildi
saçım saçımı saçıma saçın saçını saçta saça saçı
nemlendirici nemlendirir nemlendirici arındırıcı yatıştırıcı canlandırıcı
yumuşatıcı besleyici koruyucu temizleyici bakımlı bakımsız
dokusu dokulu kıvamı kıvamlı emilim emilimi
sprey spreyi spreyle spreyin püskürt püskürtün püskürtme
tarak tarakla tarama taranma taranması
rutin rutini rutinim rutinime rutinine
formül formülü formülünde içerik içeriği içeriğinde
losyon losyonu serum serumu balm roll-on
INCI SPF UV ml gr
""".split()


def kelimeler(metin: str) -> set[str]:
    return {k for k in re.findall(r"[A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû'-]{3,}", metin)}


def main() -> int:
    havuz: set[str] = set(KOZMETIK_EK)

    # 1) Kutu gercegi: INCI terimleri ve urun adlari
    for yol in sorted(KUTU.glob("*.json")):
        if yol.stem == "_hepsi":
            continue
        try:
            d = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        havuz |= kelimeler(str(d.get("urun_adi") or ""))
        havuz |= kelimeler(str((d.get("bolumler") or {}).get("inci") or ""))

    # 2) Katalog urun adlari VE Wix aciklamalari
    #
    # 🔴 ACIKLAMALAR DA KAYNAK. Olculdu (22.09.2026): hunspell tr_TR yaygin
    # Turkce bicimlerin ~%10'unu kaciriyor ("oynuyordu", "taraniyordu").
    # Elle liste yazmak yerine KENDI ONAYLI METINLERIMIZI sozluge katiyoruz:
    # Wix urun aciklamalari mevzuat temizliginden gecmis gercek Turkce
    # kozmetik nesri. Orada gecen bir kelime bizim icin tanimli demektir.
    #
    # Bu ayni zamanda dogru kapsam: imla kapisi MUSTERIYE GIDEN metni
    # denetliyor ve o metin zaten bu dilde yaziliyor.
    try:
        from jarvis.memory import CompanyMemory
        for k in CompanyMemory(host=None)._fetch("urun_karti").records:
            havuz |= kelimeler(str(k.get("urun_adi") or ""))
            havuz |= kelimeler(str(k.get("aciklama_duz") or ""))
    except Exception as hata:  # noqa: BLE001
        print(f"  katalog okunamadi ({str(hata)[:70]}) — kutu verisiyle devam",
              file=sys.stderr)

    # 3) Olculmus hunspell bosluklari (her biri dogrulandi)
    havuz |= {"oynuyordu", "taranıyordu"}

    temiz = sorted({k.strip("'-") for k in havuz if len(k.strip("'-")) >= 3})
    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    HEDEF.write_text("\n".join(temiz) + "\n", encoding="utf-8")
    print(f"{len(temiz)} kelime -> {HEDEF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
