"""Panelden gelen DEĞİŞİKLİK ÖNERİLERİNİ onay kuyruğuna hazırlar.

NEDEN VAR — ölçülen iki kırık uç
Panelde iki düğme "henüz bağlanmadı" diyordu ve doğru söylüyordu:
  · E-TİCARET → ürün alanı düzenleme ("Satış fiyatı" dahil)
  · FİYAT MATRİSİ → toplu fiyat değişikliğini onaya gönderme
İkisi de kullanıcıya dürüst davranıyordu ("hiçbir değişiklik yapılmadı"),
ama iş yarım kalıyordu.

🔴 YENİ BİR YOL İCAT EDİLMEDİ. `agency_store` ve kodlama görevleri zaten
diske ŞARTNAME yazıp `jarvis-operator create-task` ile görev açıyor; döngü
o şartnameyi okuyup öneriyi yazıyor. Aynı desen burada tekrarlanıyor:
bu modül VERİTABANINA YAZMAZ, GÖREV AÇMAZ, yalnız dosya yazar.

🔴 ONAY ≠ UYGULAMA. Sözleşmede PRICE_CHANGE ve WIX_PUBLISH için
`execution_enabled = False`. Yani bu öneriyi onaylamak Wix'te hiçbir şeyi
değiştirmez; onaylanmış bir DEĞİŞİKLİK TALEBİ kaydı oluşturur ve değişikliği
insan uygular. Arayüz bunu böyle söylemek zorunda -- "kaydedildi" demek
yalan olurdu, panelin eski hâli de bu yüzden bağlanmamıştı.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR",
                                "/opt/lcarlie/jarvis-phase2/state"))
PENDING_DIR = STATE_DIR / "agency" / "pending"

# core.ai_propose_action 'reason' alanını 2000 baytta reddediyor.
AZAMI_GEREKCE = 1900

SLUG_KALIBI = re.compile(r"^[a-z0-9-]{4,120}$")


class DegisiklikHatasi(ValueError):
    """Öneri hazırlanamadı. Mesajı kullanıcıya gösterilebilir."""


def izinli_alanlar(hafiza: Any) -> dict[str, dict[str, Any]]:
    """Değiştirilebilir alanlar — SABİT LİSTE DEĞİL, CANLI GÖRÜNÜMDEN.

    🔴 İLK SÜRÜM SABİT LİSTEYDİ VE GERÇEKLE UYUŞMUYORDU. Kodda
    `"satis_fiyati"` gibi slug'lar vardı; `mart.urun_alan_karsilastirma`
    ise Türkçe ETİKET taşıyor: 'Satış fiyatı', 'Liste fiyatı', 'Ürün adı'…
    Panel etiketi gönderiyor, arka uç slug bekliyordu: her düzenleme
    "alan listede yok" diye reddedilecekti.

    Sabit listeyi düzeltmek yetmezdi — görünüme yeni bir alan eklendiğinde
    panel DÜZENLE düğmesini gösterir, arka uç reddederdi ve bu sessiz bir
    tutarsızlık olurdu. Bu yüzden izin listesi ÖLÇÜLÜR: alan görünümde
    var mı ve en az bir platformda yazılabilir mi?

    Yazılamayan alan ('Kategori' gibi, iki platformda da false) öneriye
    bile giremez: değiştirilemeyecek bir şeyi onaya sunmak, onaylayanın
    vaktini çalmaktır.
    """
    try:
        kayitlar = hafiza._fetch("urun_alan_karsilastirma").records
    except Exception as hata:  # noqa: BLE001
        raise DegisiklikHatasi(
            f"alan listesi okunamadı, öneri hazırlanmadı: {str(hata)[:120]}"
        ) from hata
    cikti: dict[str, dict[str, Any]] = {}
    for k in kayitlar:
        ad = str(k.get("alan") or "").strip()
        if not ad or ad in cikti:
            continue
        yazilir = bool(k.get("wix_yazilabilir")) or bool(k.get("trendyol_yazilabilir"))
        if not yazilir:
            continue
        cikti[ad] = {"grup": str(k.get("grup") or ""),
                     "wix_yazilabilir": bool(k.get("wix_yazilabilir")),
                     "trendyol_yazilabilir": bool(k.get("trendyol_yazilabilir"))}
    return cikti


def _slug(parca: str) -> str:
    duz = re.sub(r"[^a-z0-9]+", "-", str(parca).casefold()).strip("-")
    return duz[:60] or "degisiklik"


def _kirp(metin: str) -> str:
    ham = metin.encode("utf-8")
    if len(ham) <= AZAMI_GEREKCE:
        return metin
    return ham[:AZAMI_GEREKCE].decode("utf-8", "ignore") + "\n…(kırpıldı)"


def _deger(x: Any) -> str:
    if x is None or x == "":
        return "(boş)"
    return str(x)[:300]


# 🔴 NİYET NEDEN PRICE_CHANGE DEĞİL — ÖLÇÜLDÜ VE BELGELİ
#
# İlk sürüm fiyat için PRICE_CHANGE, diğer alanlar için WIX_PUBLISH
# kullanıyordu. Sözleşmede ikisi de proposal_enabled=true olduğu için
# çalışacak sanılmıştı; çalışmadı:
#
#     FIREWALL_REJECTED  ERROR: invalid price payload
#     CONTEXT: PL/pgSQL function ai_propose_action(...) line 25 at RAISE
#
# Sebebi `migrations/011_trendyol_baslik_uyum.sql` içinde zaten yazılı:
#   "core.ai_propose_action HER TİP İÇİN payload şemasını kendi CASE'inde
#    doğruluyor ve tanımadığını reddediyor... kasıtlı bir güvenlik tasarımı.
#    O fonksiyon eylem güvenlik duvarının kendisidir."
#   "Bunun yerine REQUEST_HUMAN_REVIEW kullanılır: tasarımın 'bir insan buna
#    baksın' için ayırdığı yol."
#   "Payload SADECE subject_ref + reason; fazladan anahtar reddedilir."
#
# Yani PRICE_CHANGE'in kendine ait bir yük şeması var ve onu TAHMİN ETMEK
# tam da tasarımın engellediği şey. Aynı duvara çarpan bir önceki migration
# aynı kararı vermiş; yeni bir yol icat etmiyoruz.
#
# Kayıp semantik değil: eylem tipi "insan baksın" olsa da önerinin GÖVDESİ
# hangi ürünün hangi alanının ne olacağını açıkça yazıyor, ve zaten
# execution_enabled her iki tipte de false -- onay Wix'i değiştirmiyor.
NIYET = "HUMAN_REVIEW_REQUEST"


def tek_alan_onerisi(urun_id: str, urun_adi: str, alan: str,
                     eski: Any, yeni: Any, gerekce: str,
                     isteyen: str, hafiza: Any) -> dict[str, Any]:
    """Bir ürünün BİR alanı için değişiklik şartnamesi yazar."""
    alan = str(alan or "").strip()
    izinli = izinli_alanlar(hafiza)
    if alan not in izinli:
        raise DegisiklikHatasi(
            f"'{alan}' değiştirilebilir alanlar arasında değil; "
            "öneri hazırlanmadı.")
    bilgi = izinli[alan]
    if str(eski) == str(yeni):
        raise DegisiklikHatasi("Yeni değer eskisiyle aynı; öneri hazırlanmadı.")
    if not str(yeni).strip():
        raise DegisiklikHatasi("Yeni değer boş; öneri hazırlanmadı.")
    if not str(gerekce or "").strip():
        # 🔴 Gerekçe zorunlu: onaylayan insan NEDEN sorusuna cevap
        # göremeden karar veremez. `operator.decide` de karar için gerekçe
        # şart koşuyor; öneri tarafında da şart koşmak tutarlı olan.
        raise DegisiklikHatasi("Gerekçe zorunlu; öneri hazırlanmadı.")

    nerede = []
    if bilgi["wix_yazilabilir"]:
        nerede.append("Wix")
    if bilgi["trendyol_yazilabilir"]:
        nerede.append("Trendyol")
    # 🔴 İLK SATIR DÜZ TÜRKÇE BİR SORUDUR — ölçülmüş bir kusurun düzeltmesi.
    # Önceki biçim "ÜRÜN ALANI DEĞİŞİKLİĞİ — HYDRAVIE" diye açılıp alt alta
    # alan/eski/yeni yazıyordu. Sahip kuyruğa bakıp "8 ürün bizden ucuz diye
    # onay gelmiş, neyin onayı bu?" dedi ve HAKLIYDI: gözün ilk gördüğü şey
    # gerekçeydi, istenen EYLEM değil. Öneri, ne yapılacağını SORU olarak
    # söylemeden başlayamaz.
    satirlar = [
        f"{urun_adi or urun_id} ürününün “{alan}” değeri "
        f"{_deger(eski)} → {_deger(yeni)} olarak değiştirilsin mi?",
        "",
        f"ürün   : {urun_adi or urun_id}",
        f"alan   : {alan} ({bilgi['grup']})",
        f"şu an  : {_deger(eski)}",
        f"önerilen: {_deger(yeni)}",
        f"gerekçe: {str(gerekce).strip()[:600]}",
        f"nerede : {' + '.join(nerede)} tarafında değiştirilebilir",
        f"talep  : {isteyen} · panelden elle girildi",
        "",
        "ONAY = bu değişikliğin yapılmasına karar verildi. RET = mevcut değer kalsın.",
        "🔴 ONAY ≠ UYGULAMA: bu eylem tipinde yürütme kapalı "
        "(execution_enabled=false). Onay kararı kaydeder; değişikliği "
        "Wix/Trendyol panelinde insan uygular.",
    ]
    return _yaz(NIYET, _slug(f"{alan}-{urun_adi or urun_id}"),
                f"urun:{urun_id}:{alan}", "\n".join(satirlar),
                {"tur": "tek_alan", "urun_id": urun_id, "urun_adi": urun_adi,
                 "alan": alan, "eski": _deger(eski), "yeni": _deger(yeni),
                 "gerekce": gerekce, "isteyen": isteyen})


def toplu_fiyat_onerisi(satirlar: list[dict], gerekce: str,
                        isteyen: str, hafiza: Any = None) -> dict[str, Any]:
    """Fiyat matrisinden gelen toplu değişiklik şartnamesi.

    🔴 Tek bir öneri olur, satır başına bir öneri değil. Sebebi: sahip
    toplu bir karar veriyor ("şu ürünlerin fiyatı şöyle olsun"); onu otuz
    ayrı onaya bölmek kararı parçalar ve yarısı onaylanmış bir fiyat
    listesi bırakır.
    """
    temiz = []
    for s in satirlar or []:
        if not isinstance(s, dict):
            continue
        eski, yeni = s.get("eski"), s.get("yeni")
        if eski is None or yeni is None or str(eski) == str(yeni):
            continue
        temiz.append({"urun": str(s.get("urun") or s.get("urun_adi") or "?")[:80],
                      "eski": _deger(eski), "yeni": _deger(yeni)})
    if not temiz:
        raise DegisiklikHatasi("Değişen satır yok; öneri hazırlanmadı.")
    if not str(gerekce or "").strip():
        raise DegisiklikHatasi("Gerekçe zorunlu; öneri hazırlanmadı.")

    govde = [f"{len(temiz)} ürünün fiyatı aşağıdaki gibi değiştirilsin mi?",
             "",
             f"kapsam : {len(temiz)} ürün",
             f"gerekçe: {str(gerekce).strip()[:400]}",
             f"talep  : {isteyen} · fiyat matrisi önizlemesinden",
             ""]
    for s in temiz[:25]:
        govde.append(f"  · {s['urun']}: {s['eski']} → {s['yeni']}")
    if len(temiz) > 25:
        govde.append(f"  · …ve {len(temiz) - 25} ürün daha")
    govde += ["",
              "ONAY = bu fiyatların uygulanmasına karar verildi. "
              "RET = mevcut fiyatlar kalsın.",
              "🔴 ONAY ≠ UYGULAMA: yürütme kapalı; onay kararı kaydeder, "
              "fiyatı insan uygular."]
    return _yaz(NIYET, _slug(f"toplu-fiyat-{len(temiz)}"),
                f"fiyat-matrisi:{len(temiz)}", "\n".join(govde),
                {"tur": "toplu_fiyat", "satirlar": temiz,
                 "gerekce": gerekce, "isteyen": isteyen})


def _yaz(niyet: str, slug_koku: str, konu: str, gerekce: str,
         ayrinti: dict[str, Any]) -> dict[str, Any]:
    """Şartnameyi diske yazar. Veritabanına DOKUNMAZ."""
    slug = f"{slug_koku}-{secrets.token_hex(3)}"
    if not SLUG_KALIBI.match(slug):
        raise DegisiklikHatasi("geçersiz öneri adı üretildi")
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    kayit = {
        "slug": slug, "intent": niyet, "olusturuldu": time.time(),
        "ayrinti": ayrinti,
        # loop.py -> _build_agency_payload bu anahtarı okur.
        "payload": {"subject_ref": konu, "reason": _kirp(gerekce)},
    }
    yol = PENDING_DIR / f"{slug}.json"
    gecici = yol.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(kayit, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    os.replace(gecici, yol)   # yarım dosya okunmasın
    return {"slug": slug, "intent": niyet, "subject_ref": konu,
            "reason": kayit["payload"]["reason"]}
