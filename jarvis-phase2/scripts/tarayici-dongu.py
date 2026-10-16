#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TARAYICI DÖNGÜSÜ — gelen sonucu sahibin onay kuyruğuna taşır.

## Neden ayrı bir timer

Bu desen projede üç kez kurulmuş ve çalışıyor: KREATIF_BRIEF,
KREATIF_INCELEME, CODE_CHANGE_REVIEW. Hepsinde iş **döngünün DIŞINDA**
yapılır, sonuç diske yazılır, sonra `jarvis-operator create-task` ile
görev açılır; `jarvis/loop.py` o görevi kiralar ve öneriyi yazar.

Tarayıcı işi de aynı: üretim PC'de olur, bu betik yalnız **sonucu okur**
ve onay kuyruğuna koyar. Jarvis döngüsünün içinde koşmaz, çünkü bir
görsel işi dakikalar sürer ve 5 dakikalık döngüyü bloklardı.

## Yetki ayrımı -- neden `jarvis-operator` çağrılıyor

`ai_writer` (Jarvis) `core.ai_enqueue_task`'ı çağırAMAZ; o grant
tasarımca yalnız `human_approver`'dadır. Görevi açan taraf insan
otoritesidir. `jarvis-operator create-task` tam bu yüzden var ve
burada da o kullanılır -- yeni bir yol açılmaz.

## Mevzuat kapısı

Dönen metin `jarvis/tarayici.sonuc_uyum()` ile denetlenir.

🔴 BLOKLU SONUÇ DA SUNULUR, ama BLOKLU diye işaretli ve öneri metni
   "bu metin yayımlanamaz" diye başlar. Silmek, "üretilmedi" ile
   "engellendi"yi aynı gösterirdi.

🔴 ÖNERİ İÇİ BOŞ OLAMAZ. `agency_store.py`'nin kuralı: "İçi boş bir
   öneriyi onaylamak, onay değildir." Bu yüzden `reason` alanı ne
   istendiğini, ne geldiğini, hangi dosyaların üretildiğini ve sahibin
   ne yapması gerektiğini yazar.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import tarayici                                    # noqa: E402
from jarvis import tarayici_yedek                              # noqa: E402

DURUM_KOK = Path(os.environ.get(
    "TARAYICI_DURUM_DIR", str(KOK / "state" / "tarayici")))
OPERATOR = os.environ.get("JARVIS_OPERATOR_BIN",
                          "/opt/lcarlie/jarvis-phase2/bin/jarvis-operator")
ALARM = os.environ.get("LCARLIE_ALARM_BIN", "/opt/lcarlie/alarm.sh")
TABAN_URL = os.environ.get("TARAYICI_TABAN_URL", "/tarayici")

EN_COK_ISTEM_OZET = 600
EN_COK_SONUC_OZET = 2500


def slug_uret(is_id: int) -> str:
    return "tarayici-%d" % int(is_id)


def alarm(seviye: str, anahtar: str, baslik: str, detay: str = "") -> None:
    """Olayı alarm merkezine yazar. Alarm hiçbir zaman döngüyü düşürmez."""
    if not Path(ALARM).is_file():
        return
    try:
        subprocess.run([ALARM, seviye, anahtar, baslik, detay],
                       capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as hata:
        sys.stderr.write("[tarayici-dongu] alarm cagrilamadi: %s\n" % hata)


def dosyalari_tasi(is_id: int, slug: str, dosyalar: list[str]) -> list[str]:
    """Sonuç dosyalarını panelin okuyabildiği dizine kopyalar.

    🔴 TAŞINMAZ, KOPYALANIR. Kaynak `/opt/lcarlie/tarayici-cikti` altında
       kalır: panel dizini silinse bile üretilen şey kaybolmaz.
    """
    hedef_dizin = DURUM_KOK / ("%s-dosyalar" % slug)
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    konan = []
    for goreli in dosyalar or []:
        kaynak = tarayici.CIKTI_KOK / goreli
        if not kaynak.is_file():
            # Yokluğun sebebi uydurulmaz: dosya kaydı var ama disk yoksa
            # bu bir kusurdur ve öneride görünmelidir.
            konan.append("EKSIK:" + os.path.basename(goreli))
            continue
        ad = os.path.basename(goreli)
        shutil.copy2(kaynak, hedef_dizin / ad)
        konan.append(ad)
    return konan


def yedek_dene(is_: dict) -> dict | None:
    """İş düştüyse sunucudaki yedek yolu dener.

    🔴 YEDEK, TARAYICININ SONUCU GİBİ GÖSTERİLMEZ. Veritabanındaki
       `sonuc_metin` olduğu gibi kalır (tarayıcı gerçekten bir şey
       üretmedi); yedeğin çıktısı öneriye AYRI bir bölüm olarak girer ve
       nereden geldiği yazılır. İkisini aynı kefeye koymak, "ChatGPT
       böyle dedi" ile "gemini böyle dedi"yi karıştırmak olurdu.

    🔴 INSAN_GEREKLI'de de denenir: giriş istenmişse API yolu doğru
       hamledir. Ama girişin gerektiği sahibe YİNE söylenir -- yedek
       çalıştı diye oturum sorunu kaybolmaz.
    """
    if is_.get("durum") not in ("HATA", "INSAN_GEREKLI"):
        return None
    try:
        sonuc = tarayici_yedek.dene(is_.get("hedef") or "", is_.get("istem") or "")
    except tarayici_yedek.YedekYok as hata:
        return {"durum": "YEDEK_YOK", "sebep": str(hata)[:400]}
    except Exception as hata:            # noqa: BLE001 - yedek hatasi isi dusurmez
        return {"durum": "YEDEK_HATASI",
                "sebep": "%s: %s" % (type(hata).__name__, str(hata)[:300])}
    sonuc["durum"] = "BEKLEMEDE" if sonuc.get("beklemede") else "YEDEK_CALISTI"
    return sonuc


def oneri_metni(is_: dict, uyum: dict, dosyalar: list[str], slug: str,
                yedek: dict | None = None) -> str:
    """Sahibin onay kuyruğunda İLK gördüğü metin.

    Kuyrukta ne olduğunun slug okumadan anlaşılması gerekir.
    """
    satirlar: list[str] = []
    durum = is_.get("durum")

    if durum == "INSAN_GEREKLI":
        satirlar.append("⛔ TARAYICI İŞİ DURDU — İNSAN GEREKLİ")
        satirlar.append("Sebep: %s" % (is_.get("hata") or "bildirilmedi"))
        satirlar.append("")
        satirlar.append("YAPMAN GEREKEN: bilgisayarda Chrome'u aç, "
                        "ChatGPT/Claude oturumunu kontrol et (giriş istemiş "
                        "ya da bot doğrulaması çıkmış olabilir), sonra işi "
                        "yeniden ver. Worker doğrulamayı aşmaya ÇALIŞMADI.")
    elif durum == "HATA":
        satirlar.append("⚠️ TARAYICI İŞİ BAŞARISIZ (%d deneme)"
                        % int(is_.get("deneme") or 0))
        satirlar.append("Sebep: %s" % (is_.get("hata") or "bildirilmedi"))
        satirlar.append("")
        satirlar.append("YAPMAN GEREKEN: sebebi oku. Arayüz değiştiyse "
                        "handler güncellenmeli; geçici bir ağ hatasıysa işi "
                        "yeniden vermek yeter.")
    elif uyum.get("uyum_durumu") == "BLOKLU":
        satirlar.append("⛔ SONUÇ ÜRETİLDİ AMA MEVZUAT KAPISI ENGELLEDİ")
        satirlar.append("Bu metin YAYIMLANAMAZ. Aşağıda yalnız görmen için var.")
        for bulgu in uyum.get("bloklu", [])[:6]:
            satirlar.append("  • %s <- %s" % (bulgu.get("rule"), bulgu.get("matched")))
        satirlar.append("")
        satirlar.append("YAPMAN GEREKEN: iddia içeren cümleyi çıkarıp işi "
                        "yeniden verebilirsin, ya da bu sonucu reddet.")
    else:
        satirlar.append("✅ TARAYICI İŞİ TAMAMLANDI")

    satirlar.append("")
    satirlar.append("Hedef    : %s" % is_.get("hedef"))
    satirlar.append("İsteyen  : %s" % is_.get("isteyen"))
    satirlar.append("İş no    : %s" % is_.get("is_id"))
    satirlar.append("")
    satirlar.append("İSTENEN:")
    istem = (is_.get("istem") or "").strip()
    satirlar.append(istem[:EN_COK_ISTEM_OZET]
                    + (" …" if len(istem) > EN_COK_ISTEM_OZET else ""))

    sonuc = (is_.get("sonuc_metin") or "").strip()
    if sonuc:
        satirlar.append("")
        satirlar.append("GELEN METİN:")
        satirlar.append(sonuc[:EN_COK_SONUC_OZET]
                        + (" …" if len(sonuc) > EN_COK_SONUC_OZET else ""))

    gercek = [d for d in dosyalar if not d.startswith("EKSIK:")]
    eksik = [d[len("EKSIK:"):] for d in dosyalar if d.startswith("EKSIK:")]
    satirlar.append("")
    if gercek:
        satirlar.append("ÜRETİLEN DOSYALAR:")
        for ad in gercek:
            satirlar.append("  %s/%s-dosyalar/%s" % (TABAN_URL, slug, ad))
    else:
        # Yokluk gizlenmez.
        satirlar.append("ÜRETİLEN DOSYA YOK.")
    if eksik:
        satirlar.append("🔴 KAYITTA OLAN AMA DİSKTE BULUNMAYAN DOSYA: %s"
                        % ", ".join(eksik))

    ekran = is_.get("ekran_goruntusu")
    if ekran:
        satirlar.append("Ekran görüntüsü: %s/%s-dosyalar/%s"
                        % (TABAN_URL, slug, os.path.basename(ekran)))

    if uyum.get("verify"):
        satirlar.append("")
        satirlar.append("İNSAN DOĞRULAMASI İSTEYEN İFADELER:")
        for bulgu in uyum["verify"][:6]:
            satirlar.append("  • %s <- %s" % (bulgu.get("rule"), bulgu.get("matched")))

    satirlar.append("")
    if yedek:
        satirlar.append("")
        satirlar.append("--- YEDEK YOL ---")
        if yedek["durum"] == "YEDEK_CALISTI":
            satirlar.append("Tarayıcı düştü ama yedek yol üretti (%s)."
                            % yedek.get("yedek"))
            satirlar.append("🔴 Bu metin ChatGPT/Claude ARAYÜZÜNDEN DEĞİL, "
                            "yukarıda yazan yedek kaynaktan geldi.")
            yedek_metin = (yedek.get("metin") or "").strip()
            if yedek_metin:
                satirlar.append("")
                satirlar.append(yedek_metin[:EN_COK_SONUC_OZET]
                                + (" …" if len(yedek_metin) > EN_COK_SONUC_OZET
                                   else ""))
            yedek_uyum = tarayici.sonuc_uyum(yedek_metin)
            if yedek_uyum["uyum_durumu"] == "BLOKLU":
                satirlar.append("")
                satirlar.append("⛔ YEDEĞİN METNİ DE MEVZUAT KAPISINDA BLOKLU. "
                                "Yayımlanamaz.")
                for bulgu in yedek_uyum.get("bloklu", [])[:6]:
                    satirlar.append("  • %s <- %s"
                                    % (bulgu.get("rule"), bulgu.get("matched")))
            # 🔴 KAPANIS NOTU, GOSTERILEN METNE AIT OLMALI. Olculdu
            #    16.10.2026: tarayici bos dondugu icin not "Denetlenecek
            #    metin yok" diyordu -- oysa hemen ustunde yedegin
            #    urettigi metin duruyordu. Not, okuyucuya metnin
            #    denetlenmedigini soyluyordu; denetlenmisti. Kapanis notu
            #    artik yedegin incelemesinden alinir.
            if yedek_metin:
                uyum = dict(uyum)
                uyum["not"] = yedek_uyum.get("not") or uyum.get("not")
        elif yedek["durum"] == "BEKLEMEDE":
            satirlar.append("İş yedek kuyruğa alındı (%s); sonucu ayrıca gelecek."
                            % yedek.get("yedek"))
        else:
            # Yokluk sebebiyle söylenir.
            satirlar.append("Yedek yol da çalışmadı -- %s" % yedek.get("sebep"))

    satirlar.append(uyum.get("not") or "")
    return "\n".join(s for s in satirlar if s is not None)


def sonucu_sun(is_: dict) -> dict:
    """Tek işi onay kuyruğuna koyar."""
    is_id = int(is_["is_id"])
    slug = slug_uret(is_id)
    uyum = tarayici.sonuc_uyum(is_.get("sonuc_metin"))

    dosyalar = list(is_.get("sonuc_dosyalari") or [])
    if is_.get("ekran_goruntusu"):
        dosyalar.append(is_["ekran_goruntusu"])
    konan = dosyalari_tasi(is_id, slug, dosyalar)
    yedek = yedek_dene(is_)

    DURUM_KOK.mkdir(parents=True, exist_ok=True)
    kayit = {"is_id": is_id, "slug": slug, "hedef": is_.get("hedef"),
             "isteyen": is_.get("isteyen"), "durum": is_.get("durum"),
             "istem": is_.get("istem"), "sonuc_metin": is_.get("sonuc_metin"),
             "dosyalar": konan, "hata": is_.get("hata"),
             "deneme": is_.get("deneme"), "uyum": uyum, "yedek": yedek,
             "reason": oneri_metni(is_, uyum, konan, slug, yedek)}
    # Atomik yazım: loop.py bu dosyayı okurken yarım hâlini görmesin.
    gecici = DURUM_KOK / (".yaziliyor-%s.json" % slug)
    with gecici.open("w", encoding="utf-8") as d:
        json.dump(kayit, d, ensure_ascii=False, indent=2)
        d.flush()
        os.fsync(d.fileno())
    os.replace(gecici, DURUM_KOK / ("%s.json" % slug))

    # Görevi insan otoritesiyle aç.
    #
    # 🔴 TAŞIMA AÇIKÇA GEÇİRİLİR. `jarvis-operator` ortam değişkeni yoksa
    #    SSH taşımasına düşer ve sunucunun KENDİSİNDE `lcarlie` adı
    #    çözülmediği için "Could not resolve hostname lcarlie" ile düşer.
    #    İlk hâlinde bu değişken yalnız systemd biriminden MİRAS alınıyordu;
    #    betik elle çalıştırıldığında sessizce başka davranırdı. Ölçüldü
    #    16.10.2026: elle çağrıda tam bu hata alındı.
    ortam = dict(os.environ)
    ortam.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")
    sonuc = subprocess.run([OPERATOR, "create-task", "TARAYICI_SONUC", slug],
                           capture_output=True, text=True, timeout=60,
                           check=False, env=ortam)
    if sonuc.returncode:
        raise RuntimeError("gorev acilamadi: %s"
                           % ((sonuc.stderr or sonuc.stdout or "").strip()[:300]))

    tarayici._psql(
        "SELECT core.tarayici_isi_sunuldu(:'is_id'::bigint, :'slug', :'uyum');",
        "human_approver",
        degiskenler={"is_id": str(is_id), "slug": slug,
                     "uyum": uyum["uyum_durumu"]})
    return {"is_id": is_id, "slug": slug, "uyum": uyum["uyum_durumu"],
            "yedek": (yedek or {}).get("durum"),
            "dosya_adedi": len([d for d in konan if not d.startswith("EKSIK:")])}


def nabiz_denetle(sayilar: dict) -> dict | None:
    """Worker'dan haber eskiyse ve kuyrukta iş varsa alarm yazar.

    🔴 "WORKER KAPALI" DENMEZ. Nabzın eskimesinin sebebi ağ da olabilir,
       SSH anahtarı da. Gözlem yazılır, teşhis yazılmaz.
    """
    bekleyen = sayilar.get("BEKLIYOR") or 0
    n = tarayici.nabiz()
    if not bekleyen:
        return None
    if n["durum"] == "TAZE":
        return None
    alarm("UYARI", "tarayici.nabiz",
          "Tarayici kuyrugunda %d is var, worker'dan haber eski" % bekleyen,
          "nabiz durumu: %s. %s" % (n["durum"], n.get("sebep") or ""))
    return {"kod": "TARAYICI_NABIZ_ESKI", "bekleyen": bekleyen,
            "nabiz": n["durum"]}


def main() -> int:
    rapor: dict = {"sunulan": [], "hata": [], "nabiz_uyarisi": None}
    s = tarayici.sayim()
    if s["durum"] != "OKUNDU":
        # Kuyruk okunamadıysa sıfır iş VARSAYILMAZ.
        rapor["kuyruk"] = s
        alarm("DEGRADED", "tarayici.kuyruk", "Tarayici kuyrugu okunamadi",
              str(s.get("sebep"))[:300])
        print(json.dumps(rapor, ensure_ascii=False))
        return 1

    rapor["sayilar"] = s["sayilar"]
    rapor["nabiz_uyarisi"] = nabiz_denetle(s["sayilar"])

    try:
        bekleyenler = tarayici.sunulacaklar(limit=10)
    except tarayici.TarayiciHatasi as hata:
        rapor["hata"].append({"asama": "sunulacaklar", "sebep": str(hata)[:300]})
        print(json.dumps(rapor, ensure_ascii=False))
        return 1

    for is_ in bekleyenler:
        try:
            rapor["sunulan"].append(sonucu_sun(is_))
        except Exception as hata:            # noqa: BLE001 - bir iş diğerini düşürmez
            rapor["hata"].append({"is_id": is_.get("is_id"),
                                  "sebep": "%s: %s" % (type(hata).__name__,
                                                       str(hata)[:300])})
            alarm("UYARI", "tarayici.sunum",
                  "Tarayici sonucu onay kuyruguna konamadi (is %s)"
                  % is_.get("is_id"), str(hata)[:300])

    print(json.dumps(rapor, ensure_ascii=False))
    return 0 if not rapor["hata"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
