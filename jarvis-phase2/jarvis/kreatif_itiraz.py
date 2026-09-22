"""KREATİF İTİRAZI — "bu görselde logo yanlış, kiminle konuşacağım?"

Sahip 22.09.2026 sordu ve doğru cevap şuydu: o güne kadar HİÇ KİMSEYLE.
Panel görseli gösteriyor, altında dört departmanın kararı duruyordu ama
sahibin itiraz edip muhatap bulmasının yolu yoktu. Görsel beğenilmezse
tek seçenek partiyi reddetmekti; NEDEN beğenilmediği kaydedilmediği için
bir sonraki koşu aynı hatayı tekrarlıyordu.

🔴 MUHATAP SORULMAZ, TÜRETİLİR.
Sahibe "kime soralım?" diye sormak, cevabını sistemin bilmesi gereken bir
soruyu ona yüklemektir. Konu seçilir; muhatap, O GÖRSELİ GERÇEKTEN
inceleyen departmanlar arasından bulunur. İlgili departman o görseli
incelememişse bu SÖYLENİR -- uydurulmuş bir muhatap yazılmaz.

🔴 MUHATAP TAHMİN DEĞİL, KAYITTAN OKUNUR.
`inceleme.json` her görsel için hangi departmanın ne karar verdiğini ve
gerekçesini tutuyor. İtiraz açılırken o kayıt da gösterilir: departman
"ben bu görseli GEÇER dedim" mi demiş, yoksa "DÜZELT" mi? Sahip kime,
neye itiraz ettiğini görerek yazar.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

KOK = Path(os.environ.get("JARVIS_STATE_DIR",
                          "/opt/lcarlie/jarvis-phase2/state")) / "kreatif-brief"

# Konu -> hangi departman cevap verir.
# 🔴 Bu eşleme uydurma değil: `inceleme.json` içinde bu dört departman
# gerçekten karar veriyor (GRAFIK_TASARIM, KREATIF_DIREKTOR, MARKA,
# MEVZUAT). Beşinci bir muhatap yazsaydık, karşılığı olmayan bir kapıya
# yönlendirmiş olurduk.
KONU_MUHATAP: dict[str, str] = {
    # Logo, yerleşim, kırpma, renk: görseli kuran taraf.
    "LOGO": "GRAFIK_TASARIM",
    # Karede yanlış ürün: ürün fotoğrafını kareye koyan taraf.
    "URUN": "GRAFIK_TASARIM",
    # Metindeki iddia: mevzuat kapısı.
    "METIN": "MEVZUAT",
    # Ton, dil, konumlandırma.
    "MARKA": "MARKA",
    "MEVZUAT": "MEVZUAT",
    # Neyin yanlış olduğu belirsizse işin sahibi direktördür.
    "DIGER": "KREATIF_DIREKTOR",
}
# Her itirazın üst mercii: çıktının tamamından o sorumlu.
UST_MERCI = "KREATIF_DIREKTOR"
KONULAR = tuple(KONU_MUHATAP)


class ItirazHatasi(Exception):
    """Sahibin okuyabileceği, Türkçe ve sebepli hata."""


def _inceleme(parti: str) -> dict:
    yol = KOK / parti / "inceleme.json"
    if not yol.is_file():
        return {}
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - bozuk dosya bir durumdur
        return {}


def muhatap_bul(parti: str, dosya: str | None, konu: str) -> dict:
    """Bu konuda kim cevap verecek ve o görsele ne demişti.

    Dönen sözlük panelde AÇIKÇA gösterilir: sahip kime yazdığını ve o
    departmanın daha önce ne dediğini görerek itiraz eder.
    """
    konu = (konu or "").strip().upper()
    if konu not in KONU_MUHATAP:
        raise ItirazHatasi(f"konu şunlardan biri olmalı: {', '.join(KONULAR)}")
    muhatap = KONU_MUHATAP[konu]

    veri = _inceleme(parti)
    gorseller = veri.get("gorseller") or []
    hedef = None
    for g in gorseller:
        if dosya and str(g.get("dosya")) == dosya:
            hedef = g
            break
    if hedef is None and not dosya and gorseller:
        hedef = None  # parti geneli: tek görsel kaydı seçilmez

    kayit = None
    inceleyenler: list[str] = []
    if hedef:
        for i in (hedef.get("inceleme") or []):
            dep = str(i.get("departman") or "")
            inceleyenler.append(dep)
            if dep == muhatap:
                kayit = {
                    "uye": i.get("uye"), "departman": dep,
                    "karar": i.get("karar"), "gerekce": i.get("gerekce"),
                }

    cikti: dict[str, Any] = {
        "konu": konu,
        "muhatap": muhatap,
        "ust_merci": UST_MERCI,
        "inceleyen_departmanlar": inceleyenler,
        "onceki_karari": kayit,
    }
    if hedef and kayit is None:
        # 🔴 Bu cümle önemli: muhatap yine de o departmandır (konu onun
        # alanı) ama bu görseli incelememiş olması BAŞLI BAŞINA bulgudur.
        cikti["uyari"] = (f"{muhatap} bu görseli incelememiş — "
                          "inceleme zincirinde boşluk var.")
    if not veri:
        cikti["uyari"] = ("Bu partinin inceleme kaydı okunamadı; muhatap "
                          "konuya göre atandı, önceki kararı gösterilemiyor.")
    return cikti


def _yaz(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=sql, capture_output=True, text=True, timeout=20, check=False)
    return (r.stderr or "").strip() if r.returncode else ""


def _oku(sql: str) -> list[dict]:
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=20, check=False)
    if r.returncode:
        return []
    out = []
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                continue
    return out


def itiraz_ac(*, parti: str, dosya: str | None, konu: str, aciklama: str,
              acan: str) -> dict:
    """İtirazı human_approver olarak yazar. Muhatabı kendisi türetir."""
    parti = (parti or "").strip()
    if not parti:
        raise ItirazHatasi("parti belirtilmedi")
    aciklama = (aciklama or "").strip()
    if len(aciklama) < 8:
        # Veritabanı da reddediyor; burada reddetmek hatayı SQL diliyle
        # değil Türkçe söyler.
        raise ItirazHatasi("neyin yanlış olduğunu birkaç kelimeyle yazın — "
                           "muhatap neyi düzelteceğini bilmeli")

    bilgi = muhatap_bul(parti, dosya, konu)
    yuk = json.dumps({
        "parti": parti, "dosya": (dosya or "").strip() or None,
        "konu": bilgi["konu"], "aciklama": aciklama[:2000],
        "muhatap": bilgi["muhatap"], "acan": (acan or "sahip")[:80],
    }, ensure_ascii=False)
    etiket = "ki" + secrets.token_hex(8)
    if f"${etiket}$" in yuk:
        raise ItirazHatasi("kodlama çakışması, kayıt yapılmadı")
    sql = ("\\set ON_ERROR_STOP on\nBEGIN;\n"
           "SET SESSION AUTHORIZATION human_approver;\n"
           "INSERT INTO core.kreatif_itiraz"
           " (parti,dosya,konu,aciklama,muhatap,acan)\n"
           "SELECT j->>'parti', j->>'dosya', j->>'konu', j->>'aciklama',\n"
           "       j->>'muhatap', j->>'acan'\n"
           f"  FROM (SELECT ${etiket}${yuk}${etiket}$::jsonb AS j) t;\n"
           "COMMIT;\n")
    hata = _yaz(sql)
    if hata:
        raise ItirazHatasi(f"itiraz kaydedilemedi: {hata[:200]}")
    return {"ok": True, **bilgi, "aciklama": aciklama}


def liste(parti: str | None = None, yalniz_acik: bool = False) -> list[dict]:
    kosul = []
    if parti:
        güvenli = parti.replace("'", "''")
        kosul.append(f"parti = '{güvenli}'")
    if yalniz_acik:
        kosul.append("acik_mi")
    nerede = (" WHERE " + " AND ".join(kosul)) if kosul else ""
    return _oku("SELECT row_to_json(x) FROM (SELECT * FROM"
                f" mart.kreatif_itiraz_guncel{nerede} LIMIT 200) x")


def acik_itirazlar_metni(urun_parti_oneki: str) -> str:
    """Bir sonraki koşunun okuması gereken açık itirazlar.

    🔴 BU FONKSİYON OLMAZSA İTİRAZ KUTUSU ŞİKÂYET KUTUSUNA DÖNER.
    İtirazın anlamı, bir sonraki üretimin aynı hatayı tekrarlamamasıdır.
    """
    satirlar = _oku(
        "SELECT row_to_json(x) FROM (SELECT parti, dosya, konu, aciklama,"
        " muhatap FROM mart.kreatif_itiraz_guncel WHERE acik_mi"
        f" AND parti LIKE '{urun_parti_oneki.replace(chr(39), chr(39) * 2)}%'"
        " ORDER BY acildi DESC LIMIT 20) x")
    if not satirlar:
        return ""
    parcalar = [f"- [{s.get('konu')}] {s.get('dosya') or 'parti geneli'}: "
                f"{s.get('aciklama')}" for s in satirlar]
    return ("SAHİBİN AÇIK İTİRAZLARI (bu ürünün önceki görsellerinde) — "
            "bunları tekrarlama:\n" + "\n".join(parcalar))
