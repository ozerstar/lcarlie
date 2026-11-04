"""Sınırlar tek yerde; kısaltma sessiz değil, kayıtlı.

Sahip 04.11.2026: "Karakter sınırlaması hep karşımıza sorun olarak çıkıyor."
Ölçülen örnekler: sahip notu 2000'lik veritabanı sınırını aştığı için HİÇ yazılmadı;
kurul 391 teslimin 362'sini ilk 2500 karakterden yargıladı (sonuç bölümü dışarıda kaldı);
karar notu 11 ekip teslimini 1500'er karakterden okudu. Hepsi `[:N]` ile sessizce kesiliyordu.

Kural: ajanlar arası ve sahibe giden metin `[:N]` ile kesilmez.
  kisalt()     paragraf sınırında keser, ne kadar atıldığını metne yazar, kesinti.jsonl'a kaydeder.
  teslim_ozu() uzun teslimde özeti ve karar/öneri/sonuç bölümlerini korur; baştan kesmez.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Veritabanının reddettiği sınırlar (core şeması; aşınca yazma HİÇ olmaz).
DB_SINIR = {
    "oneri_sebebi": 2000,        # ai_propose_action REQUEST_HUMAN_REVIEW reason
    "karar_gerekcesi": 2000,     # ai_decide_action / ai_action_approval reason
    "taslak_cevap": 4000,        # ai_propose_action DRAFT_CUSTOMER_REPLY draft_text
    "uygulama_ozeti": 1000,      # ai_complete_action_execution summary
    "sahip_karar_notu": 4000,    # human_decide_karar note
    "tarayici_istemi": 8000,     # tarayici_isi.istem
}

_ONEMLI = re.compile(r"karar|öneri|oneri|sonuç|sonuc|aksiyon|eylem|yapılacak|yapilacak|risk|eksik", re.I)


def _kaydet(ne: str, orijinal: int, kalan: int) -> None:
    # Yol her çağrıda okunur: testler JARVIS_STATE_DIR'i geçici dizine çevirir.
    kayit = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "kesinti.jsonl"
    try:
        kayit.parent.mkdir(parents=True, exist_ok=True)
        with kayit.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "ne": ne,
                                "orijinal": orijinal, "kalan": kalan}, ensure_ascii=False) + "\n")
    except OSError:
        pass   # kayıt yazılamaması kısaltmayı durdurmaz


def kisalt(metin: str, sinir: int, *, ne: str, isaret: str = "") -> str:
    """`sinir`e sığdırır. Sığıyorsa dokunmaz; sığmıyorsa paragraf sınırında keser ve not düşer."""
    metin = metin or ""
    if len(metin) <= sinir:
        return metin
    not_ = f"\n\n… (kısaltıldı: {len(metin)} karakterin bir kısmı" + (f"; tamamı: {isaret}" if isaret else "") + ")"
    yer = max(0, sinir - len(not_))
    kes = metin[:yer]
    sinir_yeri = max(kes.rfind("\n\n"), kes.rfind("\n"))
    if sinir_yeri > yer * 0.6:
        kes = kes[:sinir_yeri]
    sonuc = kes.rstrip() + not_
    _kaydet(ne, len(metin), len(sonuc))
    return sonuc


def teslim_ozu(md: str, sinir: int, *, ne: str, isaret: str = "") -> str:
    """Uzun teslim markdown'ı: başlık + Özet + karar/öneri/sonuç bölümleri önce, kalan yer gövdeye.

    Baştan kesmek sonucu atıyordu: teslimlerde sonuç ve öneri en sonda durur.
    """
    md = md or ""
    if len(md) <= sinir:
        return md
    parcalar = re.split(r"(?m)^(?=#{1,4} )", md)
    bas, bolumler = (parcalar[0], parcalar[1:]) if parcalar and not parcalar[0].startswith("#") else ("", parcalar)
    if bolumler and bolumler[0].startswith("# "):   # teslim başlığı + künye her zaman başta
        bas += bolumler.pop(0)
    onemli = [b for b in bolumler if _ONEMLI.search(b.splitlines()[0] if b else "") or b.startswith("## Özet")]
    diger = [b for b in bolumler if b not in onemli]
    secilen = bas + "".join(onemli)
    if len(secilen) < sinir:
        secilen += "".join(diger)
    return kisalt(secilen, sinir, ne=ne, isaret=isaret)
