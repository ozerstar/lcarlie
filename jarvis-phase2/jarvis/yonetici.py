"""Yönetici kafa: her ekip teslimini kontrol eder, düzelttirir, yalnız temiz işi geçirir.

Sahip 04.11.2026: "Ekip hergün kendine düzenli iş bulsun ve yapsın, bunları yöneten bir kafa
olsun. Çıkan çıktıları da kontrol edip düzeltilmesini istesin, bana hatasız gelsin."

Ölçüm (28.10–04.11): 430 görev, teslimlerin %57'si ekibin kendi beyanıyla KISMİ ama
"teslim edildi" sayılıyordu; kalite kapısı yalnız BİÇİME bakıyordu (kelime, madde, kanıt
kimliği). Rakam ve tarih kanıtla hiç karşılaştırılmıyordu: "dün 39 sipariş, 71.061 TL"
yazan teslim geçti, oysa sipariş verisinin son günü 22.10'du. Dönen iş geri bildirim
almadan aynı istemle tekrar deneniyor, iki denemeden sonra kimsenin bakmadığı
INSAN_INCELEMESI kuyruğuna düşüyordu (197 birikti).

Akış (is_uretici.yurut her teslimden hemen sonra çağırır):
  1. olgu_denetimi  — model YOK: kanıtta izi olmayan rakam, bozuk tutar, analizde gelecek tarih.
  2. istem_denetim  — yönetici modeli teslimi görev + kabul ölçütü + kanıtla okur:
                      ONAY / DUZELT (somut düzeltme listesi) / RED.
  3. DUZELT → aynı görev düzeltme listesiyle yeniden açılır (en çok DUZELTME_TURU tur);
     tur biterse ya da RED ise görev gerekçesiyle REDDEDILDI olur. Sahipsiz kuyruk yok.
Yalnız ONAY alan teslim "teslim edildi" sayılır ve sahibe gider.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

DUZELTME_TURU = 2          # yönetici en çok bu kadar kez geri gönderir
ONAY, DUZELT, RED = "ONAY", "DUZELT", "RED"

_AYLAR = {"ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
          "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
          "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12}

# Kanıtla karşılaştırılan rakam: en az 3 basamak ya da TL/% taşıyan sayı.
_SAYI = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{3,}(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?(?=\s*(?:TL|₺|%)))")
_BOZUK_TUTAR = re.compile(r"\b\d{1,3}(?:\.\d{3})*\.\d{2}\.\d+\b|\b\d+,\d{3},\d{3}\.\d{3}\b")
_TARIH_NOKTALI = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b")
_TARIH_AYLI = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_AYLAR) + r")(?:\s+(20\d{2}))?\b", re.I)


def _rakam(s: str) -> str:
    """Biçimden bağımsız rakam izi: 71.061,50 / 71,061.50 / 71061.5 -> '7106150' gibi."""
    return re.sub(r"\D", "", s).rstrip("0") or "0"


def _kanittaki_rakamlar(kanit: str) -> set[str]:
    return {_rakam(m.group(1)) for m in _SAYI.finditer(kanit)} | {_rakam(x) for x in re.findall(r"\d{3,}", kanit)}


def olgu_denetimi(icerik: str, kanit: str, bugun: date, tip: str) -> list[str]:
    """Modelsiz olgu denetimi. Dönen her madde somut bir düzeltme isteğidir."""
    bulgular: list[str] = []
    for m in _BOZUK_TUTAR.finditer(icerik):
        bulgular.append(f"bozuk tutar yazımı: '{m.group(0)}' — tutarı tek biçimde yaz (ör. 9.289,18 TL)")
    if tip == "ANALIZ":
        # Analiz geçmişi anlatır; bugünden sonraki tarih ya uydurma ya plan karışmış demektir.
        ileri: list[str] = []
        for g, a, y in _TARIH_NOKTALI.findall(icerik):
            try:
                if date(int(y), int(a), int(g)) > bugun:
                    ileri.append(f"{g}.{a}.{y}")
            except ValueError:
                continue
        for g, ay, y in _TARIH_AYLI.findall(icerik):
            try:
                t = date(int(y) if y else bugun.year, _AYLAR[ay.casefold()], int(g))
            except (ValueError, KeyError):
                continue
            if t > bugun and y:
                ileri.append(f"{g} {ay} {y}")
        if ileri:
            bulgular.append("analizde bugünden sonraki tarih var (" + ", ".join(sorted(set(ileri))[:4])
                            + ") — analiz yalnız gerçekleşmiş veriyi anlatır; planı ayrı başlıkta yaz")
    izler = _kanittaki_rakamlar(kanit)
    sayilar = [m.group(1) for m in _SAYI.finditer(icerik)]
    # Yıllar ve küçük sıra numaraları karşılaştırmaya girmez.
    adaylar = [s for s in sayilar if not re.fullmatch(r"20\d{2}", s)]
    izsiz = [s for s in adaylar if _rakam(s) not in izler]
    if len(adaylar) >= 4 and len(izsiz) / len(adaylar) > 0.5:
        bulgular.append(f"rakamların çoğu kanıtta yok ({len(izsiz)}/{len(adaylar)}; ör. "
                        + ", ".join(list(dict.fromkeys(izsiz))[:5])
                        + ") — her rakamı kanıttan al ya da nasıl hesaplandığını yaz")
    return bulgular


DENETIM_SISTEM = (
    "Sen L'CARLIÉ şirketinin operasyon yöneticisisin. Ekiplerin teslimlerini sahibe gitmeden önce "
    "denetlersin. Ölçütün: sahip bu teslimi okuyup hatasız karar verebilir mi? Rakamlar kanıttan mı, "
    "tarih ve dönem doğru mu, görevde istenen çıktı gerçekten var mı, kabul ölçütü karşılanmış mı, "
    "Türkçe ve anlaşılır mı. Nazik ama net ol. Yalnız JSON döndür."
)


def istem_denetim(gorev: dict, departman: str, ozet: str, icerik: str, kanit: str,
                  bulgular: list[str], tur: int) -> list[dict]:
    olgu = "\n".join(f"- {b}" for b in bulgular) or "- (otomatik denetim sorun bulmadı)"
    kullanici = f"""Departman: {departman}
Görev: {gorev.get('baslik')}
Tip: {gorev.get('tip')}
İstenen çıktı: {gorev.get('cikti')}
Kabul ölçütü: {gorev.get('kabul_olcutu')}
Düzeltme turu: {tur} / {DUZELTME_TURU}

<kanit>
{kanit}
</kanit>

<teslim_ozeti>
{ozet}
</teslim_ozeti>

<teslim>
{icerik}
</teslim>

Otomatik olgu denetiminin bulguları:
{olgu}

Kararını ver:
- ONAY: teslim doğru, kanıta dayalı, istenen çıktıyı veriyor; sahibe gidebilir.
- DUZELT: düzeltilebilir hatalar var. Her düzeltme tek, somut, yapılabilir bir istek olsun
  ("3. satırdaki 71.061 TL kanıtta yok; K2'deki 22.10 tarihli satırı kullan" gibi). En çok 5 madde.
- RED: görev bu veriyle yapılamaz ya da teslim baştan yanlış; nedenini yaz.
Otomatik bulgular gerçek bir hataysa DUZELT listesine al; yanlış alarmsa yok say.
JSON:
{{"karar": "ONAY | DUZELT | RED",
  "duzeltmeler": ["..."],
  "gerekce": "1-2 cümle"}}"""
    return [{"role": "system", "content": DENETIM_SISTEM}, {"role": "user", "content": kullanici}]


def karar_ayikla(v: dict[str, Any], bulgular: list[str]) -> tuple[str, list[str], str]:
    """Model kararını doğrular. Okunamayan karar ONAY sayılmaz: otomatik bulgu varsa DUZELT."""
    karar = str(v.get("karar") or "").strip().upper().replace("İ", "I")
    duzeltmeler = [str(x).strip()[:400] for x in (v.get("duzeltmeler") or []) if str(x).strip()][:5]
    gerekce = str(v.get("gerekce") or "").strip()[:400]
    if karar not in (ONAY, DUZELT, RED):
        karar = DUZELT if bulgular else ONAY
        gerekce = gerekce or "yönetici kararı okunamadı; otomatik denetime göre karar verildi"
    if karar == DUZELT and not duzeltmeler:
        duzeltmeler = list(bulgular) or [gerekce or "teslimi kabul ölçütüne göre tamamla"]
    return karar, duzeltmeler, gerekce


def duzeltme_blogu(gorev: dict) -> str:
    """istem_yurut'a eklenir: önceki teslim + yöneticinin istediği düzeltmeler."""
    d = gorev.get("duzeltme") or {}
    if not d.get("liste"):
        return ""
    maddeler = "\n".join(f"{i}. {x}" for i, x in enumerate(d["liste"], 1))
    onceki = str(d.get("onceki") or "")
    return (f"\n\nBU İŞ YÖNETİCİDEN GERİ DÖNDÜ (düzeltme turu {d.get('tur', 1)}/{DUZELTME_TURU}). "
            f"Baştan yazma; önceki teslimi aşağıdaki düzeltmelerle düzelt ve TAMAMINI yeniden ver.\n"
            f"İstenen düzeltmeler:\n{maddeler}\n"
            + (f"<onceki_teslim>\n{onceki}\n</onceki_teslim>\n" if onceki else ""))
