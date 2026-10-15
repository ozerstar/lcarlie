#!/usr/bin/env python3
"""Yeni WhatsApp mesajlarına güvenli, tek seferlik müşteri yanıtı."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

import gelen_kutusu  # noqa: E402
from jarvis import whatsapp  # noqa: E402

DEVIR_YANITI = frozenset({"SAGLIK", "BELIRTI_ANLATIMI", "SIKAYET", "ANLASILMADI"})


def _baslangic() -> str:
    ham = os.environ.get("JARVIS_WHATSAPP_AUTO_SINCE", "")
    try:
        zaman = datetime.fromisoformat(ham)
    except ValueError:
        raise RuntimeError("otomatik yanit baslangici gecersiz") from None
    if zaman.tzinfo is None:
        raise RuntimeError("otomatik yanit baslangicinda saat dilimi yok")
    return zaman.isoformat()


def adaylar(baslangic: str) -> list[dict]:
    return gelen_kutusu._calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.id AS mesaj_id, k.id AS konusma_id
      FROM lcarlie.konusma k
      JOIN LATERAL (
        SELECT id, harici_id, zaman, yon, gonderen, metin, ek
        FROM lcarlie.mesaj WHERE konusma_id = k.id
        ORDER BY zaman DESC, id DESC LIMIT 1
      ) m ON TRUE
      WHERE k.kanal = 'whatsapp' AND k.devir_durumu = 'JARVIS'
        AND m.yon = 'gelen' AND m.gonderen = 'musteri'
        AND length(btrim(m.metin)) > 0
        AND m.harici_id LIKE 'wamid.%'
        AND m.zaman >= {gelen_kutusu._tirnak(baslangic)}::timestamptz
        AND m.zaman > now() - interval '23 hours'
        AND NOT (COALESCE(m.ek, '{{}}'::jsonb) ? 'auto_reply')
      ORDER BY m.zaman, m.id LIMIT 20
    ) x;
    """)


def sahiplen(mesaj_id: int, konusma_id: int, baslangic: str) -> bool:
    satir = gelen_kutusu._calistir(f"""
    WITH g AS (
      UPDATE lcarlie.mesaj m
         SET ek = COALESCE(m.ek, '{{}}'::jsonb) ||
                  jsonb_build_object('auto_reply', 'claimed')
       WHERE m.id = {int(mesaj_id)} AND m.konusma_id = {int(konusma_id)}
         AND NOT (COALESCE(m.ek, '{{}}'::jsonb) ? 'auto_reply')
         AND m.yon = 'gelen' AND m.gonderen = 'musteri'
         AND length(btrim(m.metin)) > 0
         AND m.harici_id LIKE 'wamid.%'
         AND m.zaman >= {gelen_kutusu._tirnak(baslangic)}::timestamptz
         AND m.zaman > now() - interval '23 hours'
         AND EXISTS (
           SELECT 1 FROM lcarlie.konusma k WHERE k.id = m.konusma_id
             AND k.kanal = 'whatsapp' AND k.devir_durumu = 'JARVIS'
             AND m.id = (SELECT son.id FROM lcarlie.mesaj son
                         WHERE son.konusma_id = k.id
                         ORDER BY son.zaman DESC, son.id DESC LIMIT 1)
         )
      RETURNING m.id
    ) SELECT row_to_json(g) FROM g;
    """)
    return bool(satir)


def hala_son(mesaj_id: int, konusma_id: int) -> bool:
    satir = gelen_kutusu._calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.id FROM lcarlie.mesaj m
      JOIN lcarlie.konusma k ON k.id = m.konusma_id
      WHERE m.id = {int(mesaj_id)} AND k.id = {int(konusma_id)}
        AND k.devir_durumu = 'JARVIS'
        AND m.ek->>'auto_reply' = 'claimed'
        AND m.zaman > now() - interval '23 hours'
        AND m.id = (SELECT son.id FROM lcarlie.mesaj son
                    WHERE son.konusma_id = k.id
                    ORDER BY son.zaman DESC, son.id DESC LIMIT 1)
    ) x;
    """)
    return bool(satir)


def bitir(mesaj_id: int, durum: str, wamid: str = "") -> None:
    gelen_kutusu._calistir(f"""
    WITH g AS (
      UPDATE lcarlie.mesaj
         SET ek = COALESCE(ek, '{{}}'::jsonb) ||
                  jsonb_build_object('auto_reply', {gelen_kutusu._tirnak(durum)},
                                     'auto_reply_wamid', {gelen_kutusu._tirnak(wamid)})
       WHERE id = {int(mesaj_id)} AND ek->>'auto_reply' = 'claimed'
      RETURNING id
    ) SELECT row_to_json(g) FROM g;
    """)


def yanit_plani(taslak: dict) -> tuple[bool, bool]:
    sinif = taslak.get("sinif")
    metin = (taslak.get("metin") or "").strip()
    if sinif == "DURDURMA":
        return False, True
    if taslak.get("devredilmeli"):
        return bool(metin) and sinif in DEVIR_YANITI, True
    if not taslak.get("uretildi") or not taslak.get("gonderilebilir") or not metin:
        return False, True
    return True, False


def isle(aday: dict, baslangic: str) -> str:
    mesaj_id = int(aday["mesaj_id"])
    konusma_id = int(aday["konusma_id"])
    if not sahiplen(mesaj_id, konusma_id, baslangic):
        return "atlandi"
    devret = False
    try:
        taslak = gelen_kutusu.taslak(konusma_id)
        gonder, devret = yanit_plani(taslak)
        if not hala_son(mesaj_id, konusma_id):
            bitir(mesaj_id, "stale")
            return "stale"
        if not gonder:
            bitir(mesaj_id, "handoff")
            if devret:
                gelen_kutusu.durum_yaz(konusma_id, "INSANDA", taslak.get("sebep"))
            return "handoff"
        metin = taslak["metin"]
        if "dijital asistanı" not in metin:
            metin += "\n\n— L'CARLIÉ dijital asistanı"
        sonuc = whatsapp.gonder(
            gelen_kutusu.telefon_bul(konusma_id), metin,
            onay_kaynagi=whatsapp.ONAY_OTOMATIK, konusma_id=konusma_id)
        bitir(mesaj_id, "sent", sonuc.get("wamid") or "")
        if devret:
            gelen_kutusu.durum_yaz(konusma_id, "INSANDA", taslak.get("sebep"))
        return "sent_handoff" if devret else "sent"
    except Exception as hata:  # noqa: BLE001 - hata konusmayi INSANDA birakir
        bitir(mesaj_id, "failed")
        gelen_kutusu.durum_yaz(konusma_id, "INSANDA", "OTOMATIK_YANIT_HATASI")
        print(f"mesaj_id={mesaj_id} sonuc=failed hata_tipi={type(hata).__name__}")
        return "failed"


def main() -> None:
    if os.environ.get("JARVIS_WHATSAPP_AUTO_REPLY") != "1":
        print("otomatik yanit kapali")
        return
    if not whatsapp.gonderme_acik():
        raise RuntimeError("WhatsApp gonderme kapali")
    baslangic = _baslangic()
    for aday in adaylar(baslangic):
        sonuc = isle(aday, baslangic)
        print(f"mesaj_id={aday['mesaj_id']} sonuc={sonuc}")


if __name__ == "__main__":
    main()
