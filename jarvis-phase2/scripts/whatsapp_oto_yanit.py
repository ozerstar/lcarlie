#!/usr/bin/env python3
"""Yeni WhatsApp mesajlarına güvenli, tek seferlik müşteri yanıtı."""
from __future__ import annotations

import os
import json
import sys
import time
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

import gelen_kutusu  # noqa: E402
from jarvis import whatsapp  # noqa: E402

DEVIR_YANITI = frozenset({"SAGLIK", "BELIRTI_ANLATIMI", "SIKAYET", "ANLASILMADI",
                          "KARGO_TAKIP"})
IDLE_SCAN_INTERVAL = 60
IDLE_SCAN_MARKER = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "whatsapp-auto-idle-scan"


def aktif_sohbet_var() -> bool:
    return bool(gelen_kutusu._calistir("""
    SELECT row_to_json(x) FROM (
      SELECT k.id FROM lcarlie.konusma k
      WHERE k.kanal = 'whatsapp' AND k.devir_durumu = 'JARVIS'
        AND k.son_mesaj >= now() - interval '15 minutes'
      LIMIT 1
    ) x;
    """))


def tarama_gerekli() -> bool:
    if aktif_sohbet_var():
        return True
    try:
        return time.time() - IDLE_SCAN_MARKER.stat().st_mtime >= IDLE_SCAN_INTERVAL
    except OSError:
        return True


def bos_tarama_kaydet() -> None:
    try:
        IDLE_SCAN_MARKER.touch()
    except OSError:
        pass


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
                  jsonb_build_object('auto_reply', 'claimed',
                                     'auto_claimed_at', now())
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


def uzayan_claimler() -> list[dict]:
    return gelen_kutusu._calistir("""
    SELECT row_to_json(x) FROM (
      SELECT m.id AS mesaj_id, m.konusma_id, k.devir_durumu,
             m.id = (SELECT son.id FROM lcarlie.mesaj son
                     WHERE son.konusma_id = m.konusma_id
                     ORDER BY son.zaman DESC, son.id DESC LIMIT 1) AS son_mesaj
      FROM lcarlie.mesaj m JOIN lcarlie.konusma k ON k.id = m.konusma_id
      WHERE k.kanal = 'whatsapp' AND m.ek->>'auto_reply' = 'claimed'
        AND COALESCE((m.ek->>'auto_claimed_at')::timestamptz, m.zaman)
            < now() - interval '2 minutes'
      ORDER BY m.zaman LIMIT 50
    ) x;
    """)


def gonderim_kaydi(mesaj_id: int) -> dict | None:
    try:
        with whatsapp.DEFTER.open(encoding="utf-8") as dosya:
            for satir in dosya:
                try:
                    kayit = json.loads(satir)
                except ValueError:
                    continue
                if (kayit.get("kaynak_mesaj_id") == mesaj_id
                        and kayit.get("sonuc") == "GONDERILDI"):
                    return kayit
    except OSError:
        pass
    return None


def uzayanlari_incele() -> None:
    for kayit in uzayan_claimler():
        mesaj_id = int(kayit["mesaj_id"])
        gonderim = gonderim_kaydi(mesaj_id)
        bitir(mesaj_id, "sent" if gonderim else "uncertain",
              (gonderim or {}).get("wamid") or "")
        if not gonderim and kayit["devir_durumu"] == "JARVIS" and kayit["son_mesaj"]:
            gelen_kutusu._calistir(f"""
            WITH g AS (
              UPDATE lcarlie.konusma k SET devir_durumu = 'INSANDA',
                  devir_sebep = 'OTOMATIK_YANIT_BELIRSIZ',
                  devir_zaman = now(), guncelleme = now()
              WHERE k.id = {int(kayit['konusma_id'])} AND k.devir_durumu = 'JARVIS'
                AND {mesaj_id} = (SELECT son.id FROM lcarlie.mesaj son
                    WHERE son.konusma_id = k.id
                    ORDER BY son.zaman DESC, son.id DESC LIMIT 1)
              RETURNING k.id
            ) SELECT row_to_json(g) FROM g;
            """)
        print(f"mesaj_id={mesaj_id} sonuc={'reconciled' if gonderim else 'uncertain_handoff'}")


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
            onay_kaynagi=whatsapp.ONAY_OTOMATIK, konusma_id=konusma_id,
            kaynak_mesaj_id=mesaj_id)
        bitir(mesaj_id, "sent", sonuc.get("wamid") or "")
        if devret:
            gelen_kutusu.durum_yaz(konusma_id, "INSANDA", taslak.get("sebep"))
        return "sent_handoff" if devret else "sent"
    except Exception as hata:  # noqa: BLE001 - hata konusmayi INSANDA birakir
        gonderim = gonderim_kaydi(mesaj_id)
        bitir(mesaj_id, "sent" if gonderim else "uncertain",
              (gonderim or {}).get("wamid") or "")
        gelen_kutusu.durum_yaz(konusma_id, "INSANDA", "OTOMATIK_YANIT_HATASI")
        print(f"mesaj_id={mesaj_id} sonuc={'sent_handoff' if gonderim else 'uncertain_handoff'} "
              f"hata_tipi={type(hata).__name__}")
        return "sent_handoff" if gonderim else "uncertain_handoff"


def main() -> None:
    if os.environ.get("JARVIS_WHATSAPP_AUTO_REPLY") != "1":
        print("otomatik yanit kapali")
        return
    if not whatsapp.gonderme_acik():
        raise RuntimeError("WhatsApp gonderme kapali")
    baslangic = _baslangic()
    uzayanlari_incele()
    if not tarama_gerekli():
        return
    for aday in adaylar(baslangic):
        sonuc = isle(aday, baslangic)
        print(f"mesaj_id={aday['mesaj_id']} sonuc={sonuc}")
    bos_tarama_kaydet()


if __name__ == "__main__":
    main()
