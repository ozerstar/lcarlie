# -*- coding: utf-8 -*-
"""YEDEK YOL — tarayıcı handler'ı düştüğünde işi kurtarır.

## Neden gerekli

ChatGPT ve Claude'un web arayüzü haber vermeden değişir; ayrıca o
arayüzleri otomatikleştirmek kullanım şartlarına aykırı olabilir. Yani
handler katmanı **kırılgan olduğu bilinerek** yazıldı. Kırıldığında işin
kaybolmaması için her hedefin bir yedeği var.

## 🔴 YEDEK SUNUCUDA KOŞAR, PC'DE DEĞİL

Yedek yollar (model sağlayıcı zinciri, ComfyUI kuyruğu) sunucuda yaşar;
PC'deki worker onları çağıramaz. Bu yüzden yedek, worker'ın bir parçası
DEĞİL: iş `HATA`ya düştükten sonra `scripts/tarayici-dongu.py` burayı
dener. Sıra şudur:

    PC'de tarayıcı -> HATA -> sunucuda yedek -> yine olmazsa sahibe HATA

## 🔴 ÖLÇÜLDÜ (16.10.2026) — HER HEDEFİN YEDEĞİ VAR DEĞİL

    claude_chat    YEDEK VAR     providers.generate() çağrılabilir
    chatgpt_chat   YEDEK VAR     aynı zincir
    chatgpt_image  YEDEK YOK*    * ComfyUI kuyruğu duruyor ama onu işleyen
                                 PC-2 worker'ının son raporu 04.10.2026.
                                 Higgsfield anahtarı sunucuda HİÇ YOK.

`chatgpt_image` için "yedek var" demek, işi kimsenin bakmadığı bir
kuyruğa atıp başarılı saymak olurdu. Burada yapılan şey: ComfyUI
kuyruğuna ancak PC-2 raporu TAZE ise yazmak, değilse "yedek yok" demek.
Yokluğu sebebiyle birlikte söylemek, bu projede tekrar eden kök hatanın
(`lcarlie-durum-ayrimi-kapisi`) tam karşılığıdır.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

YEDEK_ACIK = os.environ.get("TARAYICI_YEDEK", "1") == "1"

# PC-2 raporu bu süreden eskiyse ComfyUI kuyruğu "işlenmiyor" sayılır.
# `webconsole/sistem.py` ile aynı eşik (BAYAT_ESIGI_S) kullanılır; ikinci
# bir sayı tanımlamak, iki yerde iki farklı tanım demekti.
PC2_BAYAT_ESIGI_S = 180.0

GORSEL_KUYRUK = Path(os.environ.get("LCARLIE_KUYRUK", "/opt/lcarlie/gorsel-kuyruk"))
HOSTS_DIR = Path(os.environ.get(
    "JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "hosts"


class YedekYok(RuntimeError):
    """Bu hedef için çalışan bir yedek yol yok. Sebep mesajda."""


# --------------------------------------------------------------------------
# METİN: mevcut sağlayıcı zinciri
# --------------------------------------------------------------------------
def _metin_yedegi(istem: str) -> dict[str, Any]:
    """İşi model sağlayıcı zincirine verir.

    `kademe="muhakeme"` seçilir, çünkü bu metin sahibin onayına ve
    muhtemelen yayına gider; hızlı kademe sınıflandırma için.
    """
    from . import providers
    try:
        sonuc = providers.generate(
            [{"role": "user", "content": istem}],
            max_tokens=1200, kademe="muhakeme",
            is_anahtari="tarayici-yedek")
    except providers.NoProvider as hata:
        raise YedekYok("sağlayıcı zincirinde çalışan model yok: %s" % hata) from None
    metin = (sonuc.get("text") or sonuc.get("content") or "").strip()
    if not metin:
        raise YedekYok("sağlayıcı boş metin döndürdü")
    return {"metin": metin, "dosyalar": [],
            "yedek": "model-zinciri:%s" % (sonuc.get("model") or "?")}


# --------------------------------------------------------------------------
# GÖRSEL: ComfyUI kuyruğu — ANCAK işleyen makine TAZE ise
# --------------------------------------------------------------------------
def _pc2_tazeligi() -> tuple[str, float | None]:
    """PC-2 raporunun tazeliği. Sözlük `sistem.py` ile aynı."""
    yol = HOSTS_DIR / "pc2.json"
    if not yol.is_file():
        return "RAPOR_YOK", None
    try:
        import datetime
        veri = json.loads(yol.read_text(encoding="utf-8"))
        damga = veri.get("olcum_utc")
        if not damga:
            return "RAPOR_YOK", None
        olcum = datetime.datetime.fromisoformat(damga.replace("Z", "+00:00"))
        yas = (datetime.datetime.now(datetime.timezone.utc) - olcum).total_seconds()
    except (OSError, ValueError, KeyError):
        return "RAPOR_YOK", None
    return ("BAYAT" if yas > PC2_BAYAT_ESIGI_S else "TAZE"), yas


def _gorsel_yedegi(istem: str) -> dict[str, Any]:
    durum, yas = _pc2_tazeligi()
    if durum != "TAZE":
        # 🔴 KUYRUĞA YAZIP "YEDEĞE DÜŞTÜ" DEMEK YASAK. Kuyruk duruyor ama
        #    onu işleyen worker'dan haber yoksa iş orada bekler ve sahip
        #    "yedek çalıştı" sanır. Yokluk, sebebiyle söylenir.
        raise YedekYok(
            "görsel yedeği yok: ComfyUI kuyruğunu işleyen PC-2'nin raporu %s%s. "
            "Higgsfield anahtarı da sunucuda tanımlı değil."
            % (durum, (" (%.0f sn önce)" % yas) if yas else ""))

    if not (GORSEL_KUYRUK / "bekleyen").is_dir():
        raise YedekYok("görsel kuyruğu yok: %s" % GORSEL_KUYRUK)

    # Kuyruğa yazma mantığı TEKRAR YAZILMAZ: panelin kullandığı
    # `webconsole/isler.is_ekle` atomik yazımı ve zorunlu alan kontrolünü
    # zaten yapıyor. İkinci bir yazıcı, ikinci bir kusur demekti.
    import sys
    kok = str(Path(__file__).resolve().parent.parent / "webconsole")
    if kok not in sys.path:
        sys.path.insert(0, kok)
    import isler                                        # noqa: PLC0415
    kayit = isler.is_ekle(str(GORSEL_KUYRUK), istem,
                          isteyen="tarayici-yedek")
    return {"metin": "", "dosyalar": [],
            "yedek": "comfyui-kuyruk:%s" % kayit["id"],
            "beklemede": True}


YEDEKLER = {
    "claude_chat": _metin_yedegi,
    "chatgpt_chat": _metin_yedegi,
    "chatgpt_image": _gorsel_yedegi,
}


def dene(hedef: str, istem: str) -> dict[str, Any]:
    """Hedefin yedeğini dener. Yedek yoksa `YedekYok` yükseltir."""
    if not YEDEK_ACIK:
        raise YedekYok("yedek yol kapalı (TARAYICI_YEDEK=1 değil)")
    islev = YEDEKLER.get(hedef)
    if not islev:
        raise YedekYok("bu hedefin tanımlı yedeği yok: %r" % (hedef,))
    return islev(istem)
