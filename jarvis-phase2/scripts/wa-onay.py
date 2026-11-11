#!/usr/bin/env python3
"""Bekleyen onayları sahibe WhatsApp'tan gönderir, düğme yanıtıyla karar verir.

AKIŞ
  1) core.ai_get_pending_actions()'taki YENİ öneri -> şablon
     `lcarlie_onay_bekliyor_v1` + "Onayla" / "Reddet" düğmeleri.
  2) Sahip düğmeye basar -> webhook -> meta-kuyruk-yukle -> lcarlie.mesaj
     (ek.button_payload = "onay:<id>:<nonce>" ya da "red:<id>:<nonce>").
  3) Bu betik yükü okur, panelle AYNI yoldan karar verir:
     OperatorSession.decide(..., expected_hash=gönderimdeki parmak izi).

🔴 KİMLİK: yalnız sahibin numarasının konuşmasındaki düğme yanıtı okunur VE
   yükteki tek kullanımlık nonce bu betiğin o öneri için ürettiğiyle
   birebir eşleşmelidir. Yazıyla "onayla" demek hiçbir şey yapmaz; nonce
   yalnız sahibin telefonuna giden mesajın düğmesinde vardır.
🔴 PARMAK İZİ: karar, mesajdaki öneriye verilir. Öneri gönderimden sonra
   değiştiyse decide reddeder ve sahibe panel söylenir.
🔴 TEKRAR YOK: gönderimden ÖNCE durum "gonderiliyor" yazılır. Çökme olursa
   o öneri WhatsApp'a bir daha gitmez (panelde durur) -- iki mesaj
   gitmesinden iyidir.
🔴 İLK KOŞU: o an bekleyen öneriler "eski" sayılır, toplu mesaj atılmaz.
🔴 kreatif-brief onayı panelde görsel üretimini başlatır (app.py
   _kreatif_uretimi_baslat). O tetik burada kopyalanmadı; böyle bir öneri
   WhatsApp'tan onaylanmaz, sahibe panel söylenir.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

import gelen_kutusu  # noqa: E402
from jarvis import whatsapp  # noqa: E402
from jarvis.haberci import SAHIP_TELEFON  # noqa: E402
from jarvis.operator import OperatorSession  # noqa: E402

SABLON = os.environ.get("WA_ONAY_SABLON", "lcarlie_onay_bekliyor_v1")
DURUM = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "wa-onay.json"
EN_FAZLA_GONDERIM = 5          # bir koşuda; birikmiş kuyruk telefonu boğmasın
TEKRAR_ARALIGI = 600           # Meta hatasından sonra yeniden deneme (sn)
EN_FAZLA_DENEME = 12
YUK = re.compile(r"^(onay|red):([0-9]{1,12}):([0-9a-f]{16})$")
MEVZUAT_YEDEK = "içerik denetimi nedeniyle özet panelde"


# ------------------------------------------------------------------- durum
def durum_oku() -> dict | None:
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def durum_yaz(durum: dict) -> None:
    tanimlayici, gecici = tempfile.mkstemp(prefix=".wa-onay-", dir=DURUM.parent)
    try:
        with os.fdopen(tanimlayici, "w", encoding="utf-8") as dosya:
            json.dump(durum, dosya, ensure_ascii=False)
            dosya.flush()
            os.fsync(dosya.fileno())
        os.chmod(gecici, 0o600)
        os.replace(gecici, DURUM)
    finally:
        if os.path.exists(gecici):
            os.unlink(gecici)


# ---------------------------------------------------------------- gönderim
def _tek_satir(metin: str, sinir: int = 180) -> str:
    metin = re.sub(r"\s+", " ", (metin or "").replace("**", "")).strip()
    return metin if len(metin) <= sinir else metin[:sinir - 1].rstrip() + "…"


def ozetle(oneri: dict) -> tuple[str, str]:
    """(konu, özet): "KURUL KARARI · TASARIM", "Görsel üret: …"."""
    neden = str((oneri.get("payload") or {}).get("reason") or "")
    satirlar = [s.strip() for s in neden.splitlines()
                if s.strip() and not s.strip().startswith("Dayanak:")]
    tur = str(oneri.get("action_type") or "ÖNERİ")
    if len(satirlar) >= 2:
        return _tek_satir(satirlar[0], 80), _tek_satir(satirlar[1])
    return _tek_satir(tur, 80), _tek_satir(satirlar[0] if satirlar else "Yeni bir öneri var.")


def gonder_bir(oneri: dict, kayit: dict) -> None:
    kimlik = str(oneri["action_id"])
    konu, ozet = ozetle(oneri)
    yukler = [f"onay:{kimlik}:{kayit['nonce']}", f"red:{kimlik}:{kayit['nonce']}"]
    try:
        sonuc = whatsapp.sablon_gonder(SAHIP_TELEFON, SABLON, ["#" + kimlik, konu, ozet],
                                       onay_kaynagi=whatsapp.ONAY_OTOMATIK,
                                       dugme_yukleri=yukler)
    except whatsapp.GondermeReddedildi as hata:
        if not str(hata).startswith("mevzuat kapisi"):
            raise
        sonuc = whatsapp.sablon_gonder(SAHIP_TELEFON, SABLON,
                                       ["#" + kimlik, konu, MEVZUAT_YEDEK],
                                       onay_kaynagi=whatsapp.ONAY_OTOMATIK,
                                       dugme_yukleri=yukler)
    kayit.update({"durum": "gonderildi", "wamid": sonuc.get("wamid") or "",
                  "konu": konu, "zaman": int(time.time())})


def yenileri_gonder(op: OperatorSession, durum: dict) -> None:
    bekleyen = op.list_pending()
    oneriler = durum.setdefault("oneriler", {})
    gonderilen = 0
    simdi = int(time.time())
    for oneri in bekleyen:
        kimlik = str(oneri["action_id"])
        kayit = oneriler.get(kimlik)
        if kayit is None:
            kayit = {"durum": "yeni", "nonce": secrets.token_hex(8),
                     "parmak_izi": oneri.get("fingerprint") or "",
                     "konu_ref": str((oneri.get("payload") or {}).get("subject_ref") or ""),
                     "deneme": 0}
            oneriler[kimlik] = kayit
        elif not (kayit.get("durum") == "yeni"   # önceki koşuda sınıra takılan
                  or (kayit.get("durum") == "hata"
                      and kayit.get("deneme", 0) < EN_FAZLA_DENEME
                      and simdi - kayit.get("son_deneme", 0) >= TEKRAR_ARALIGI)):
            continue
        if gonderilen >= EN_FAZLA_GONDERIM:
            break
        kayit.update({"durum": "gonderiliyor", "deneme": kayit.get("deneme", 0) + 1,
                      "son_deneme": simdi})
        durum_yaz(durum)
        try:
            gonder_bir(oneri, kayit)
            gonderilen += 1
            print(f"action_id={kimlik} gonderildi")
        except whatsapp.GondermeReddedildi as hata:
            kayit.update({"durum": "hata", "sebep": str(hata)[:200]})
            print(f"action_id={kimlik} gonderilemedi: {str(hata)[:120]}")
        durum_yaz(durum)


# ------------------------------------------------------------------- karar
def dugme_yanitlari() -> list[dict]:
    return gelen_kutusu._calistir(f"""
    SELECT row_to_json(x) FROM (
      SELECT m.id AS mesaj_id, m.konusma_id, m.ek->>'button_payload' AS yuk
      FROM lcarlie.mesaj m JOIN lcarlie.konusma k ON k.id = m.konusma_id
      WHERE k.kanal = 'whatsapp' AND k.harici_id = {gelen_kutusu._tirnak(SAHIP_TELEFON)}
        AND m.yon = 'gelen'
        AND m.ek->>'button_payload' ~ '^(onay|red):[0-9]+:[0-9a-f]{{16}}$'
        AND NOT (m.ek ? 'wa_onay')
        AND m.zaman > now() - interval '7 days'
      ORDER BY m.zaman, m.id LIMIT 20
    ) x;
    """)


def isaretle(mesaj_id: int, deger: str, *, sahiplen: bool = False) -> bool:
    kosul = "NOT (COALESCE(ek, '{}'::jsonb) ? 'wa_onay')" if sahiplen \
        else "ek->>'wa_onay' = 'claimed'"
    return bool(gelen_kutusu._calistir(f"""
    WITH g AS (
      UPDATE lcarlie.mesaj
         SET ek = COALESCE(ek, '{{}}'::jsonb) ||
                  jsonb_build_object('wa_onay', {gelen_kutusu._tirnak(deger)})
       WHERE id = {int(mesaj_id)} AND {kosul}
      RETURNING id
    ) SELECT row_to_json(g) FROM g;
    """))


def karar_ver(op: OperatorSession, durum: dict, yuk: str) -> tuple[str, str]:
    """(sonuç kodu, sahibe gidecek cevap)."""
    eslesme = YUK.match(yuk or "")
    if not eslesme:
        return "gecersiz", ""
    tur, kimlik, nonce = eslesme.groups()
    kayit = (durum.get("oneriler") or {}).get(kimlik)
    if not kayit or not hmac.compare_digest(str(kayit.get("nonce") or ""), nonce):
        return "nonce_tutmadi", f"⚠️ #{kimlik} için bu düğme tanınmadı. Kararı Jarvis panelinden verin."
    if str(kayit.get("durum", "")).startswith("karar:"):
        return "tekrar", f"ℹ️ #{kimlik} için kararınız zaten kaydedildi."
    karar = "APPROVED" if tur == "onay" else "REJECTED"
    if karar == "APPROVED" and kayit.get("konu_ref", "").startswith("kreatif-brief:"):
        return "panel_gerekli", (f"ℹ️ #{kimlik} onaylanınca görsel üretimi başlar; "
                                 "bu onay yalnız Jarvis panelinden verilebilir.")
    canli = op.inspect(int(kimlik))
    if canli is None:
        kayit["durum"] = "karar:DISARIDA"
        return "bekleyen_degil", f"ℹ️ #{kimlik} artık onay beklemiyor (panelden karar verilmiş ya da süresi dolmuş)."
    if (canli.get("fingerprint") or "") != kayit.get("parmak_izi"):
        return "degisti", f"⚠️ #{kimlik} size gönderildikten sonra değişti. Lütfen panelden bakın."
    sonuc = op.decide(int(kimlik), karar, "WhatsApp düğmesi (sahip)",
                      expected_hash=kayit["parmak_izi"])
    if not sonuc.get("confirmed"):
        return "dogrulanamadi", f"⚠️ #{kimlik} kararı doğrulanamadı. Panelden kontrol edin."
    kayit["durum"] = "karar:" + karar
    isaret = "✅ onaylandı" if karar == "APPROVED" else "❌ reddedildi"
    return karar, f"{isaret}: #{kimlik} ({kayit.get('konu') or 'öneri'})"


def kararlari_isle(op: OperatorSession, durum: dict) -> None:
    for satir in dugme_yanitlari():
        mesaj_id = int(satir["mesaj_id"])
        if not isaretle(mesaj_id, "claimed", sahiplen=True):
            continue
        try:
            sonuc, cevap = karar_ver(op, durum, satir.get("yuk") or "")
        except Exception as hata:  # noqa: BLE001 - karar belirsizse sahibe panel söylenir
            sonuc, cevap = "hata", "⚠️ Kararınız işlenemedi. Lütfen Jarvis panelinden kontrol edin."
            print(f"mesaj_id={mesaj_id} karar hatasi: {type(hata).__name__}")
        durum_yaz(durum)
        isaretle(mesaj_id, sonuc)
        print(f"mesaj_id={mesaj_id} sonuc={sonuc}")
        if cevap:
            try:
                whatsapp.gonder(SAHIP_TELEFON, cevap, onay_kaynagi=whatsapp.ONAY_OTOMATIK,
                                konusma_id=int(satir["konusma_id"]))
            except whatsapp.GondermeReddedildi as hata:
                print(f"mesaj_id={mesaj_id} cevap gonderilemedi: {str(hata)[:120]}")


def main() -> None:
    if not whatsapp.gonderme_acik():
        print("WhatsApp gonderme kapali")
        return
    op = OperatorSession(host=None)
    durum = durum_oku()
    if durum is None:
        durum = {"oneriler": {str(o["action_id"]): {"durum": "eski"}
                              for o in op.list_pending()}}
        durum_yaz(durum)
        print(f"ilk kosu: {len(durum['oneriler'])} bekleyen oneri eski sayildi")
        return
    kararlari_isle(op, durum)
    yenileri_gonder(op, durum)
    durum_yaz(durum)


if __name__ == "__main__":
    main()
