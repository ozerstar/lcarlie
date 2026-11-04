#!/usr/bin/env python3
"""Idefix kategori atamasi — 36 urun icin yaprak kategori secimi.

KARAR KAYNAGI
Her satir urunun KENDI tanimina gore secildi (Wix aciklamasi + INCI + hacim),
klasor adina veya kelime benzerligine gore degil. Secim gerekcesi satirda
duruyor; katilmadigin satiri degistirmek icin SECIM sozlugunu duzelt.

Kategori komisyonu ve zorunlu ozellikleri BELIRLER -- bu yuzden "yakin olan"
degil, urunun fiilen ne oldugu esas alindi.

Cikti: urunler.csv'ye kategori_id + kategori_secimi sutunlarini yazar,
       KATEGORI-SECIMI.md olarak gerekceli tabloyu uretir.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

KAT_JSON = Path("/tmp/idefix-kat.json")
CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
RAPOR = Path("/opt/lcarlie/idefix-hazirlik/KATEGORI-SECIMI.md")

# barkod -> (yaprak yolunun SONU, gerekce, varsa ikinci aday)
SECIM: dict[str, tuple[str, str, str]] = {
    "8684869609363": ("Bebek Cilt Bakımı > Bebek Krem & Losyon",
                      "5 ml balm, bebek cildinde kuruluk hissi", ""),
    "8684869609387": ("Bebek Ağız ve Diş Bakımı > Bebek ve Çocuk Diş Macunu",
                      "bebek/cocuk dis bakim jeli", ""),
    "8684869609356": ("Bebek Duş & Banyo > Bebek Şampuanı",
                      "bebek sampuani", ""),
    "8684869609523": ("Bebek Cilt Bakımı > Bebek Krem & Losyon",
                      "bebek vucut losyonu", ""),
    "8684869609530": ("Bebek Cilt Bakımı > Bebek Güneş Bakım Ürünleri",
                      "bebek gunes kremi", "Çocuk Güneş Ürünleri"),
    "8684869609394": ("Ağız Bakım > Diş Macunu",
                      "dis macunu (etiket: Natural Toothpaste)", ""),
    "8684869609301": ("Parfüm ve Deodorant > Vücut Spreyi",
                      "kendi tanimi 'vucut spreyi'; neem/sitronella aromatik",
                      "Alerji ve Enfeksiyon Urunleri -- iddia dogurur, SECILMEDI"),
    "8684869609196": ("Cilt Bakım Yağları > Bakım Yağı",
                      "10 ml roll-on, hodan yagi bazli cilt bakimi", ""),
    "8684869609080": ("Yüz Bakımı > Tonik",
                      "ferahlatici tonik sprey", ""),
    "8684869609578": ("Cilt Bakım Yağları > Bakım Yağı",
                      "10 ml aromatik bakim roll-on", ""),
    "8684869609066": ("Vücut Bakımı > Nemlendiriciler",
                      "bariyer ve koruyucu bakim kremi", ""),
    "8684869609288": ("Ayak Tırnak Bakımı > Ayak Kremi",
                      "ure + sogut kabugu, sertlesmis bolgede yumusaklik",
                      "Nasır ve Mantar Ürünleri -- tedavi cagristirir, SECILMEDI"),
    "8684869609103": ("Ayak Tırnak Bakımı > Ayak Kremi",
                      "ayak ve tirnak bakim kremi", ""),
    "8684869609516": ("Vücut Bakımı > Nemlendiriciler",
                      "SAHIP KARARI 23.10: vucut kremleri",
                      "Masaj, Spa & Wellness -- HIZMET kategorisi, SECILMEDI"),
    "8684869609073": ("Vücut Bakımı > Selülit Giderici / Sıkılaştırıcılar ve Çatlak Bakımı",
                      "iz gorunumu / yenileyici bakim", "Nemlendiriciler"),
    "8684869609554": ("Vücut Bakımı > Nemlendiriciler",
                      "SAHIP KARARI 23.10: vucut kremleri",
                      "Masaj, Spa & Wellness -- HIZMET kategorisi, SECILMEDI"),
    "8684869609561": ("Vücut Bakımı > Selülit Giderici / Sıkılaştırıcılar ve Çatlak Bakımı",
                      "gerilme bolgeleri (catlak) bakimi", ""),
    "8684869609271": ("Vücut Bakımı > Nemlendiriciler",
                      "bacak ve vucut bakim kremi", ""),
    "8684869609400": ("Vücut Bakımı > Nemlendiriciler",
                      "SAHIP KARARI 23.10: vucut kremleri",
                      "Masaj, Spa & Wellness -- HIZMET kategorisi, SECILMEDI"),
    "8684869609370": ("Saç Bakım Ürünleri > Saç Kremi",
                      "durulanmayan tarama kolaylastirici sprey",
                      "Saç Serum ve Yağı"),
    "8684869609127": ("Kadın Pedleri & Hijyen Ürünleri > İntim Bakım Ürünü",
                      "kadinlara ozel intim bakim kremi",
                      "Cinsel Jel > Vajinal Krem -- yanlis raf, SECILMEDI"),
    "8684869609158": ("Saç Bakım Ürünleri > Saç Serum ve Yağı",
                      "sac bakim yagi", ""),
    "8684869609233": ("Yüz Bakımı > Yüz Kremi",
                      "yogun nemlendirici yuz kremi", ""),
    "8684869609318": ("Kadın Pedleri & Hijyen Ürünleri > İntim Bakım Ürünü",
                      "hassas bolge bakim kremi", ""),
    "8684869609547": ("Vücut Bakımı > Nemlendiriciler",
                      "SAHIP KARARI 23.10: vucut kremleri",
                      "Masaj, Spa & Wellness -- HIZMET kategorisi, SECILMEDI"),
    "8684869609141": ("Yüz Bakımı > Yüz Kremi",
                      "SAHIP KARARI 23.10: yuz kremi",
                      "Göğüs Bakım Ürünleri -- doldurulabilir ozellik yok"),
    "8684869609134": ("Cilt Bakım > Dudak Bakımı",
                      "dudak nemlendirici balm", ""),
    "8684869609295": ("Yüz Bakımı > Yüz Temizleyici",
                      "yuz temizleme kopugu", ""),
    "8684869609585": ("Cilt Bakım Yağları > Bakım Yağı",
                      "10 ml bitki yaglari roll-on, tatli badem bazli", ""),
    "8684869609325": ("Bebek Cilt Bakımı > Bebek Krem & Losyon",
                      "bebek bez bolgesi bakim kremi",
                      "Bebek Pişik Tedavi Ürünleri -- 'tedavi' adi iddia tasir, SECILMEDI"),
    "8684869609172": ("Göz Bakımı > Göz Kremi",
                      "goz cevresi bakim roll-on", "Göz Serumu"),
    "8684869609165": ("Ağız Bakım > Ağız Gargara ve Spreyleri",
                      "agiz bakim spreyi", ""),
    # 🔴 DUZELTILDI 22.10: "Gece Bakim Kremi" adina bakip Yuz Kremi secilmisti;
    # urunun kendi tanimi "gun sonu BACAK bakiminda kullanilir" diyor. Yuz
    # urunu degil. Ad yaniltti, tanim duzeltti.
    "8684869609202": ("Vücut Bakımı > Nemlendiriciler",
                      "kendi tanimi: gun sonu bacak bakimi (yuz urunu DEGIL)",
                      "Yüz Kremi -- ad yaniltiyor, SECILMEDI"),
    "8684869609608": ("Genel Temizlik > Oda Kokusu, Koku Giderici",
                      "KOZMETIK DEGIL: yatak/perde/doselik yuzeye uygulanir",
                      "Çok Amaçlı Temizleyiciler -- temizleyici degil, SECILMEDI"),
    "8684869609097": ("Güneş Ürünleri > Güneş Krem ve Losyonları",
                      "SPF 30+ gunes kremi", ""),
    "8684869609110": ("Erkek Cilt, Vücut Bakımı > Erkek Nemlendirici, Bakım",
                      "erkek bakim kremi", ""),
}


def yapraklar(agac, yol=()):
    for d in agac or []:
        y = yol + (d["name"],)
        alt = d.get("subs") or []
        if alt:
            yield from yapraklar(alt, y)
        else:
            yield d["id"], " > ".join(y)


def main() -> int:
    agac = json.loads(KAT_JSON.read_text(encoding="utf-8"))
    tum = list(yapraklar(agac))

    cozum: dict[str, tuple[int, str]] = {}
    for barkod, (son, _, _) in SECIM.items():
        esler = [(kid, yol) for kid, yol in tum if yol.endswith(son)]
        if len(esler) != 1:
            print(f"HATA {barkod}: '{son}' -> {len(esler)} eslesme")
            for kid, yol in esler[:5]:
                print("   ", kid, yol)
            return 1
        cozum[barkod] = esler[0]

    satirlar = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))
    alanlar = list(satirlar[0].keys())
    if "kategori_id" not in alanlar:
        alanlar.insert(alanlar.index("kategori_secimi"), "kategori_id")

    eksik = []
    for s in satirlar:
        b = s["barkod"]
        if b in cozum:
            kid, yol = cozum[b]
            s["kategori_id"] = str(kid)
            s["kategori_secimi"] = yol
        else:
            eksik.append(b)
            s["kategori_id"] = ""
    if eksik:
        print("SECIMI OLMAYAN BARKODLAR:", eksik)
        return 1

    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        y = csv.DictWriter(f, fieldnames=alanlar, delimiter=";")
        y.writeheader()
        y.writerows(satirlar)

    satir_md = ["# Idefix kategori seçimi — 36 ürün", "",
                "Seçim ürünün kendi tanımına göre yapıldı (Wix açıklaması + INCI + hacim).",
                "Kategori **komisyonu ve zorunlu özellikleri belirler**; katılmadığın satırı",
                "`idefix-kategori-ata.py` içindeki `SECIM` sözlüğünden değiştir.", "",
                "| Ürün | Kategori | ID | Gerekçe | Değerlendirilen ikinci aday |",
                "|---|---|---|---|---|"]
    for s in sorted(satirlar, key=lambda r: r["urun_adi_wix"]):
        b = s["barkod"]
        _, gerekce, ikinci = SECIM[b]
        kisa = s["kategori_secimi"].split(" > ", 1)[1] if " > " in s["kategori_secimi"] else s["kategori_secimi"]
        satir_md.append(f"| {s['urun_adi_wix'][:30]} | {kisa} | `{s['kategori_id']}` "
                        f"| {gerekce} | {ikinci or '—'} |")
    satir_md += ["",
                 "## Dikkat edilecekler", "",
                 "- 🔴 **SOFTGUARD kozmetik değil**: yatak/perde/döşemelik yüzeylere uygulanıyor,",
                 "  bu yüzden Süpermarket > Ev & Temizlik altına kondu. Mağazanın bu kategoriye",
                 "  ürün ekleme izni olup olmadığı DOĞRULANMADI (panel: 'yalnızca izin verilen",
                 "  kategoriler seçilebilir').",
                 "- Adı 'tedavi' veya hastalık çağrıştıran raflar bilerek seçilmedi",
                 "  (MINISOOTH için Pişik Tedavi, DERMACORN için Nasır ve Mantar).",
                 "- Bir sonraki adım: her kategorinin ZORUNLU özelliklerini çekmek",
                 "  (`GET /pim/category-attribute/{categoryId}`) — doldurulamayan zorunlu",
                 "  özellik varsa o kategori yüklenemez.", ""]
    RAPOR.write_text("\n".join(satir_md), encoding="utf-8")

    print(f"atanan: {len(cozum)}/36")
    print(f"farkli kategori: {len(set(k for k, _ in cozum.values()))}")
    print(f"rapor: {RAPOR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
