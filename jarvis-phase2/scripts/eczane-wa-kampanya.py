#!/usr/bin/env python3
"""Eczane WhatsApp kampanyası: dakikada bir çalışır, her çalışmada EN FAZLA bir mesaj.

Sahip 13.11.2026: "Ankara'daki tüm eczanelerin telefonlarına WhatsApp olarak
göndermeni istiyorum ama banlanmayacağımız bir düzenle", "sabah 10 akşam 6'ya
kadar dakikada 1 tane", "geri dönüşleri de not etmeni istiyorum". Numara:
mevcut 0544 544 21 15 (sahip seçti; kargo/teyit de bu numarada — fren bu yüzden sıkı).

Her çalışmada sırayla:
  1. Teslim durumları (webhook teslimat.jsonl) -> core.eczane_gonderim
  2. Eczacı cevapları -> core.eczane_etkilesim (YANIT / CIKIS) + sahibe push
  3. Frenler: pencere, durdurma dosyası, şablon onayı, kalite puanı, günlük
     Meta limiti, "istemiyorum" oranı, başarısız teslim oranı
  4. Sıradaki eczaneye tek şablon mesajı

🔴 Ortak whatsapp.sablon_gonder URL düğmesi parametresi taşımıyor; o modül
başka oturumlarda da değiştiği için ona dokunulmadı. Aynı kapılar (mevzuat
denetimi, gönderme anahtarı, defter) buradan çağrılır.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
from jarvis import whatsapp  # noqa: E402

TR = timezone(timedelta(hours=3))
SABLON = os.environ.get("ECZANE_WA_SABLON", "lcarlie_eczane_tanisma_v1")
WABA = os.environ.get("ECZANE_WA_WABA", "2418585758581265")
IL = os.environ.get("ECZANE_WA_IL", "Ankara")
PENCERE = (10, 18)                    # 10:00 dahil, 18:00 hariç; hafta içi
DURUM = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "eczane-wa"
DURDUR = DURUM / "DURDUR"             # varsa gönderim yapılmaz (fren ya da elle)
TESLIMAT = Path(os.environ.get("JARVIS_STATE_DIR", str(KOK / "state"))) / "meta_webhook" / "teslimat.jsonl"
TIER = {"TIER_50": 50, "TIER_250": 250, "TIER_1K": 1000, "TIER_10K": 10000,
        "TIER_100K": 100000, "TIER_UNLIMITED": 100000}
SAAT_TAVAN = 60                       # dakikada 1 -> saatte en fazla 60
# Fren eşikleri (en az ORNEK teslimden sonra değerlendirilir)
ORNEK = 40
RED_ORANI = 0.05                      # "İstemiyorum" / teslim
BASARISIZ_ORANI = 0.35                # sabit hatların çoğunda WhatsApp yok; bu
                                      # oran yüksek olabilir, ama ani sıçrama işaret
KATALOG = "https://www.lcarlie.shop/_files/ugd/92cdbf_9a439a7872ad438ca0e0c7f6f908fe87.pdf"
ONIZLEME = ("L’CARLIÉ, doğal ve bitkisel içeriklerle formüle edilmiş bir dermokozmetik markasıdır. "
            "Serimizi eczanenizde tanıtmak isteriz: 15 dakikalık bir ziyarette ürünleri elinizde "
            "inceleyebilir, eczaneye özel koşulları konuşabiliriz.")


def psql(sql: str, **v: str) -> list[dict]:
    arg = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At",
           "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1"]
    for k, d in v.items():
        arg += ["-v", "%s=%s" % (k, d)]
    p = subprocess.run(arg, input=sql, capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:400])
    return [json.loads(s) for s in p.stdout.splitlines() if s.strip().startswith(("{", "["))]


def graph(yol: str) -> dict:
    jeton = whatsapp._env("META_WHATSAPP_TOKEN")
    r = urllib.request.Request("https://graph.facebook.com/v21.0/" + yol,
                               headers={"Authorization": "Bearer " + jeton})
    with urllib.request.urlopen(r, timeout=20) as y:
        return json.loads(y.read().decode())


def onbellek(ad: str, saniye: int, uret):
    DURUM.mkdir(parents=True, exist_ok=True)
    f = DURUM / (ad + ".json")
    try:
        d = json.loads(f.read_text())
        if time.time() - d["t"] < saniye:
            return d["v"]
    except (OSError, ValueError, KeyError):
        pass
    v = uret()
    f.write_text(json.dumps({"t": time.time(), "v": v}))
    return v


def push(baslik: str, metin: str) -> None:
    try:
        from jarvis import haberci
        haberci.push_gonder(baslik, metin, "eczane-wa")
    except Exception as e:  # noqa: BLE001 - bildirim gitmese de kayıt durur
        print("push gitmedi:", e)


def durdur(sebep: str) -> None:
    if not DURDUR.exists():
        DURUM.mkdir(parents=True, exist_ok=True)
        DURDUR.write_text(datetime.now(TR).isoformat() + " " + sebep + "\n")
        push("⛔ Eczane WhatsApp kampanyası DURDU", sebep)
    print("DURDU:", sebep)


# ------------------------------------------------------------------ 1. teslimat
def teslimat_isle() -> None:
    ofs_dosya = DURUM / "teslimat.ofs"
    try:
        ofs = int(ofs_dosya.read_text())
    except (OSError, ValueError):
        ofs = 0
    if not TESLIMAT.exists():
        return
    if TESLIMAT.stat().st_size < ofs:
        ofs = 0                                  # dosya döndürülmüş
    sira = {"SENT": 1, "DELIVERED": 2, "READ": 3, "FAILED": 9}
    with TESLIMAT.open(encoding="utf-8") as f:
        f.seek(ofs)
        olaylar = []
        for satir in f:
            try:
                o = json.loads(satir)
            except ValueError:
                continue
            olaylar.append(o)
        ofs_yeni = f.tell()
    for o in olaylar:
        d = str(o.get("durum") or "").upper()
        if d not in sira:
            continue
        # Durum yalnız ileri gider (READ geldikten sonra geç DELIVERED ezmez); FAILED her zaman yazılır.
        psql("UPDATE core.eczane_gonderim SET durum = :'d', hata_kodu = nullif(:'h',''), guncellendi = now()"
             " WHERE wamid = :'w' AND (:'d' = 'FAILED' OR CASE durum WHEN 'GONDERILDI' THEN 0 WHEN 'SENT' THEN 1"
             " WHEN 'DELIVERED' THEN 2 WHEN 'READ' THEN 3 ELSE 9 END < :'s'::int);",
             d=d, h=str(o.get("hata_kodu") or ""), w=str(o.get("wamid") or ""), s=str(sira[d]))
    ofs_dosya.write_text(str(ofs_yeni))


# --------------------------------------------------------------- 2. cevaplar
def cevaplari_isle() -> None:
    """Kampanya konuşmalarına gelen her mesaj eczane kaydına bir kez işlenir."""
    yeni = psql("""
    SELECT row_to_json(x) FROM (
      SELECT m.id AS mesaj_id, (k.notlar->>'eczane_hedef_id')::bigint AS hedef_id,
             m.metin, m.ek->>'button_payload' AS dugme, h.eczane, h.ilce, m.zaman
      FROM lcarlie.mesaj m
      JOIN lcarlie.konusma k ON k.id = m.konusma_id
      JOIN core.eczane_hedef h ON h.id = (k.notlar->>'eczane_hedef_id')::bigint
      WHERE k.kanal = 'whatsapp' AND k.notlar ? 'eczane_hedef_id'
        AND m.yon = 'gelen' AND m.zaman > now() - interval '30 days'
        AND NOT EXISTS (SELECT 1 FROM core.eczane_etkilesim e
                        WHERE e.hedef_id = h.id AND e.ayrinti->>'mesaj_id' = m.id::text)
      ORDER BY m.zaman
    ) x;""")
    for c in yeni:
        red = (c.get("dugme") or "").startswith("ECZ_RED") or (c.get("metin") or "").strip().lower() in (
            "istemiyorum", "i̇stemiyorum")
        tur = "CIKIS" if red else "YANIT"
        psql("INSERT INTO core.eczane_etkilesim (hedef_id, tur, ayrinti) VALUES (:'h', :'t', :'a');"
             + (" UPDATE core.eczane_hedef SET durum = 'CIKTI', guncellendi = now() WHERE id = :'h';" if red else
                " UPDATE core.eczane_hedef SET durum = 'ILGILENDI', guncellendi = now()"
                " WHERE id = :'h' AND durum IN ('YENI','GONDERILDI');"),
             h=str(c["hedef_id"]), t=tur,
             a=json.dumps({"kanal": "whatsapp", "mesaj_id": str(c["mesaj_id"]),
                           "metin": (c.get("metin") or "")[:1000]}, ensure_ascii=False))
        if not red:
            push("💬 Eczane cevap verdi", "%s%s: %s" % (
                c["eczane"], " (" + c["ilce"] + ")" if c.get("ilce") else "", (c.get("metin") or "")[:180]))
        print(tur, c["hedef_id"])


# ------------------------------------------------------------------- 3. frenler
def sablon_onayli() -> bool:
    def uret():
        d = graph("%s/message_templates?name=%s&fields=name,status" % (WABA, SABLON))
        return [t.get("status") for t in d.get("data", []) if t.get("name") == SABLON]
    return "APPROVED" in onbellek("sablon", 600, uret)


def numara_durumu() -> dict:
    pid = whatsapp._env("META_WHATSAPP_PHONE_NUMBER_ID")
    return onbellek("numara", 1800, lambda: graph(pid + "?fields=quality_rating,messaging_limit_tier"))


def frenler() -> int | None:
    """Gönderilebilecekse bugünkü kalan hakkı döner, değilse None."""
    simdi = datetime.now(TR)
    if simdi.weekday() >= 5 or not (PENCERE[0] <= simdi.hour < PENCERE[1]):
        return None
    if DURDUR.exists():
        return None
    if not whatsapp.gonderme_acik():
        print("gönderme anahtarı kapalı")
        return None
    if not sablon_onayli():
        print("şablon henüz onaylı değil")
        return None
    nd = numara_durumu()
    if nd.get("quality_rating") not in ("GREEN", "UNKNOWN", None):
        durdur("Numara kalite puanı %s — kargo/teyit hattını korumak için durdu." % nd.get("quality_rating"))
        return None
    o = psql("""SELECT row_to_json(x) FROM (SELECT
        count(*) FILTER (WHERE gonderildi > now() - interval '24 hours' AND durum <> 'REDDEDILDI') AS son24,
        count(*) FILTER (WHERE gonderildi > now() - interval '1 hour' AND durum <> 'REDDEDILDI') AS son1s,
        count(*) FILTER (WHERE durum IN ('DELIVERED','READ')) AS teslim,
        count(*) FILTER (WHERE durum = 'FAILED') AS basarisiz,
        count(*) FILTER (WHERE durum <> 'REDDEDILDI') AS toplam,
        (SELECT count(*) FROM core.eczane_etkilesim e WHERE e.tur = 'CIKIS'
           AND e.ayrinti->>'kanal' = 'whatsapp') AS red
      FROM core.eczane_gonderim WHERE kanal = 'whatsapp' AND sablon = :'s') x;""", s=SABLON)[0]
    if o["teslim"] >= ORNEK and o["red"] / o["teslim"] > RED_ORANI:
        durdur("'İstemiyorum' oranı %%%d (%d/%d teslim) eşiği aştı." % (
            100 * o["red"] / o["teslim"], o["red"], o["teslim"]))
        return None
    if o["toplam"] >= ORNEK and o["basarisiz"] / o["toplam"] > BASARISIZ_ORANI and o["teslim"] < o["basarisiz"]:
        durdur("Başarısız teslim çok yüksek (%d/%d)." % (o["basarisiz"], o["toplam"]))
        return None
    limit = TIER.get(nd.get("messaging_limit_tier") or "", 250)
    # Kargo/teyit gibi diğer işletme mesajlarına pay bırak: limitin %90'ı.
    kalan = int(limit * 0.9) - o["son24"]
    if kalan <= 0 or o["son1s"] >= SAAT_TAVAN:
        return None
    return kalan


# ------------------------------------------------------------------ 4. gönderim
def baslik_hali(ad: str) -> str:
    s = re.sub(r"\s+", " ", ad or "").strip()
    s = " ".join(k[:1] + k[1:].replace("I", "ı").replace("İ", "i").lower() for k in s.split(" "))
    s = s.replace("Eczanesi̇", "Eczanesi").replace("Eczanesı", "Eczanesi")
    if "eczane" not in s.lower():
        s += " Eczanesi"
    return s[:60]


SIRADAKI = """
SELECT row_to_json(x) FROM (
  WITH tel AS (
    SELECT h.id, h.eczane, h.anahtar, h.son_nobet,
           (SELECT t FROM raw.eczane_kaynak k, unnest(k.telefonlar) t
             WHERE k.hedef_id = h.id AND left(t,1) = '5' ORDER BY k.kaynak LIMIT 1) AS cep,
           right(regexp_replace(coalesce(h.telefon,''),'\\D','','g'),10) AS sabit
    FROM core.eczane_hedef h
    WHERE h.il = :'il' AND h.durum IN ('YENI','GONDERILDI','ILGILENDI')
      AND NOT ('TEST' = ANY (h.etiketler))
      AND NOT EXISTS (SELECT 1 FROM core.eczane_gonderim g
                      WHERE g.hedef_id = h.id AND g.kanal = 'whatsapp' AND g.sablon = :'s')
  )
  SELECT id, eczane, anahtar, '90' || coalesce(cep, sabit) AS telefon, cep IS NOT NULL AS cep_mi
  FROM tel
  WHERE length(coalesce(cep, sabit)) = 10
    AND NOT EXISTS (SELECT 1 FROM core.eczane_gonderim g
                    WHERE g.telefon = '90' || coalesce(tel.cep, tel.sabit)
                      AND g.kanal = 'whatsapp' AND g.sablon = :'s' AND g.durum <> 'REDDEDILDI')
  ORDER BY (cep IS NULL), (son_nobet IS NULL), id
  LIMIT 1
) x;"""


def gonder_bir() -> None:
    adaylar = psql(SIRADAKI, il=IL, s=SABLON)
    if not adaylar:
        print("gönderilecek eczane kalmadı")
        return
    a = adaylar[0]
    ad = baslik_hali(a["eczane"])
    if whatsapp.denetle(ad + " | " + ONIZLEME):
        psql("INSERT INTO core.eczane_gonderim (hedef_id, telefon, sablon, durum, hata)"
             " VALUES (:'h', :'t', :'s', 'REDDEDILDI', 'mevzuat kapısı');", h=str(a["id"]), t=a["telefon"], s=SABLON)
        return
    # Eczacının cevabı satış botuna değil insana düşsün: konuşma önceden INSANDA açılır.
    # Var olan konuşmanın devir kararı ezilmez, yalnız eczane kimliği not edilir.
    psql("INSERT INTO lcarlie.konusma (kanal, harici_id, musteri_ref, notlar, devir_durumu)"
         " VALUES ('whatsapp', :'t', :'t', jsonb_build_object('kaynak','eczane_kampanya','eczane_hedef_id', :'h'::bigint), 'INSANDA')"
         " ON CONFLICT (kanal, harici_id) DO UPDATE SET notlar = lcarlie.konusma.notlar"
         " || jsonb_build_object('eczane_hedef_id', :'h'::bigint), guncelleme = now();",
         t=a["telefon"], h=str(a["id"]))
    jeton = whatsapp._env("META_WHATSAPP_TOKEN")
    pid = whatsapp._env("META_WHATSAPP_PHONE_NUMBER_ID")
    yuk = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": a["telefon"],
           "type": "template", "template": {"name": SABLON, "language": {"code": "tr"}, "components": [
               {"type": "body", "parameters": [{"type": "text", "text": ad}]},
               {"type": "button", "sub_type": "url", "index": "0",
                "parameters": [{"type": "text", "text": a["anahtar"]}]},
               {"type": "button", "sub_type": "quick_reply", "index": "1",
                "parameters": [{"type": "payload", "payload": "ECZ_RED:%s" % a["id"]}]}]}}
    veri, sebep, ayrinti = whatsapp._meta_cagir(pid, jeton, yuk)
    kayit = {"ts": datetime.now(TR).isoformat(), "tur": "sablon", "sablon": SABLON,
             "telefon_son4": a["telefon"][-4:], "onay_kaynagi": "sahip-panel:eczane-kampanya"}
    if sebep:
        kayit.update({"sonuc": "REDDEDILDI", "sebep": sebep})
        whatsapp._defter_yaz(kayit)
        psql("INSERT INTO core.eczane_gonderim (hedef_id, telefon, sablon, durum, hata)"
             " VALUES (:'h', :'t', :'s', 'REDDEDILDI', :'e');",
             h=str(a["id"]), t=a["telefon"], s=SABLON, e=(str(sebep) + " " + json.dumps(ayrinti, ensure_ascii=False))[:500])
        print("REDDEDILDI", a["id"], sebep)
        # Meta hız/limit hatası: o gün daha fazla deneme yapma
        if any(k in json.dumps(ayrinti or "") for k in ("131056", "131048", "130429", "131049")):
            durdur("Meta limit/hız uyarısı: %s" % json.dumps(ayrinti, ensure_ascii=False)[:200])
        return
    wamid = str(((veri or {}).get("messages") or [{}])[0].get("id") or "")
    kayit.update({"sonuc": "GONDERILDI", "wamid": wamid})
    whatsapp._defter_yaz(kayit)
    psql("INSERT INTO core.eczane_gonderim (hedef_id, telefon, sablon, wamid, durum)"
         " VALUES (:'h', :'t', :'s', :'w', 'GONDERILDI');"
         " INSERT INTO core.eczane_etkilesim (hedef_id, tur, ayrinti) VALUES (:'h', 'GONDERILDI',"
         " jsonb_build_object('kanal','whatsapp','sablon', :'s','wamid', :'w'));"
         " UPDATE core.eczane_hedef SET durum = 'GONDERILDI', guncellendi = now() WHERE id = :'h' AND durum = 'YENI';",
         h=str(a["id"]), t=a["telefon"], s=SABLON, w=wamid)
    print("GONDERILDI", a["id"], ad, "cep" if a["cep_mi"] else "sabit")


def main() -> None:
    DURUM.mkdir(parents=True, exist_ok=True)
    teslimat_isle()
    cevaplari_isle()
    if "--kuru" in sys.argv:
        print("kuru koşu: kalan hak", frenler(), "sıradaki", psql(SIRADAKI, il=IL, s=SABLON))
        return
    if frenler() is not None:
        gonder_bir()


if __name__ == "__main__":
    main()
