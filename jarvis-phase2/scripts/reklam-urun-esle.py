#!/usr/bin/env python3
"""Reklam kreatifinden ürünü çıkarır ve `core.reklam_urun`'e yazar.

NEDEN VAR
Müşteri "fiyatı nedir?" diye yazıyor ve hangi ürünü kastettiğini SÖYLEMİYOR
(ölçüldü: 540 mesajın 0'ında ürün adı var). Tek sinyal, geldiği reklam.
Reklamın ADI da yetmiyor ("k9", "K2", "6"); ürünü söyleyen şey kreatif
GÖVDESİ.

🔴 ELLE KONULAN EŞLEŞMEYE DOKUNMAZ
`kaynak='ELLE'` satırları insanın kararıdır ve bu betik onları atlar.
Bu projede kurulum betikleri elle yapılmış değişiklikleri koşulsuz ezdiği
için bir kez canlı kırıldı; aynı hata tekrarlanmıyor.

🔴 EŞLEŞMEYENE ÜRÜN UYDURMAZ
Kapsanmayan reklam `kaynak='YOK'` olarak işaretlenir. "YOK" ile satırın hiç
olmaması farklı şeydir: ilki "bakıldı, ürün yok", ikincisi "henüz bakılmadı".
Ürünsüz reklamdan gelen müşteriye doğru davranış, ona hangi ürün olduğunu
sormaktır.

Çalıştırma:
    JARVIS_MEMORY_TRANSPORT=local-docker \\
      venv/bin/python scripts/reklam-urun-esle.py [--kuru]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.satis_dialog import _sade  # noqa: E402

PSQL = ["docker", "exec", "-i", "lcarlie-postgres",
        "psql", "-U", "n8n", "-d", "n8n", "-tA"]


def _sorgu(sql: str) -> list[str]:
    sonuc = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise SystemExit(f"psql hatası: {sonuc.stderr[:400]}")
    return [s for s in sonuc.stdout.split("\n") if s.strip()]


def kod_uret(urunler: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Ürün adından ayırt edici kod. Kod ne kadar uzunsa yanlış eşleşme o kadar az.

    🔴 "BABY RESCUE" tek kelimeye ("BABY") indirgenirse BABYDENT, BABYSOL ve
    BABYSHOWER ile ÇAKIŞIR ve reklam yanlış ürüne bağlanır -- müşteriye
    yanlış ürünün fiyatı gider. Bu yüzden ilk kelime BAŞKA bir üründe de
    geçiyorsa iki kelime alınır.
    """
    ham: list[tuple[str, str, list[str]]] = []
    for urun_id, ad in urunler:
        kelimeler = [k for k in re.split(r"[ ·(|+]+", (ad or "").strip()) if k]
        if not kelimeler:
            continue
        ham.append((urun_id, ad, kelimeler))

    # 🔴 BELİRSİZLİK "aynı ilk kelime" DEĞİL, "başka ürünün adının İÇİNDE
    # geçiyor" demektir. Test bunu yakaladı: "BABY RESCUE"un ilk kelimesi
    # "BABY" ve başka hiçbir ürünün ilk kelimesi "BABY" değil -- ama "baby",
    # BABYSOL / BABYSHOWER / BABYDENT adlarının İÇİNDE geçiyor. Sayım bunu
    # göremez, alt dize kontrolü görür.
    tam_adlar = [(_sade(ad), urun_id) for urun_id, ad, _ in ham]

    def belirsiz(kod: str, kendi_id: str) -> bool:
        return any(kod in sade_ad and uid != kendi_id
                   for sade_ad, uid in tam_adlar)

    kodlar: dict[str, tuple[str, str]] = {}
    for urun_id, ad, kelimeler in ham:
        ilk = _sade(kelimeler[0])
        if len(ilk) < 4:
            continue
        kod = ilk
        if belirsiz(kod, urun_id) and len(kelimeler) > 1:
            kod = _sade(" ".join(kelimeler[:2]))
        # İki kelime de ayırt etmiyorsa bu ürün için kod ÜRETİLMEZ.
        # Belirsiz bir kodla eşleştirmek, yanlış ürünün fiyatını göndermektir.
        if belirsiz(kod, urun_id):
            continue
        kodlar[kod] = (urun_id, ad)
    return kodlar


def urun_esle(sade_metin: str, kodlar: dict[str, tuple[str, str]]
              ) -> tuple[str, str, str] | None:
    """Metne en UZUN eşleşen kod kazanır.

    "BABY RESCUE" varken "BABY" ile yetinmek yanlış ürüne bağlar; uzunluğa
    göre sıralamak bu tercihi deterministik yapar.
    """
    adaylar = sorted((k for k in kodlar if k in sade_metin), key=len, reverse=True)
    if not adaylar:
        return None
    urun_id, urun_adi = kodlar[adaylar[0]]
    return urun_id, urun_adi, adaylar[0]


def urun_kodlari() -> dict[str, tuple[str, str]]:
    satirlar = _sorgu("select urun_id||'\x01'||urun_adi from mart.urun_karti;")
    return kod_uret([tuple(s.split("\x01", 1)) for s in satirlar if "\x01" in s])


def reklam_metinleri() -> dict[str, str]:
    sql = ("select ad_id||'\x01'||regexp_replace("
           "coalesce(ad_adi,'')||' '||coalesce(kreatif_adi,'')||' '||"
           "coalesce(baslik,'')||' '||coalesce(govde,''),"
           "E'[\\n\\r\\t]+',' ','g') from raw.meta_kreatif;")
    metinler: dict[str, str] = {}
    for satir in _sorgu(sql):
        if "\x01" not in satir:
            continue
        ad_id, metin = satir.split("\x01", 1)
        metinler[ad_id] = metinler.get(ad_id, "") + " " + metin
    return metinler


def elle_konulanlar() -> set[str]:
    return {s.strip() for s in
            _sorgu("select ad_id from core.reklam_urun where kaynak='ELLE';")}


def main() -> None:
    kuru = "--kuru" in sys.argv
    kodlar = urun_kodlari()
    metinler = reklam_metinleri()
    korunan = elle_konulanlar()
    print(f"ürün kodu: {len(kodlar)} · reklam: {len(metinler)} · "
          f"elle konulmuş (dokunulmayacak): {len(korunan)}")

    yazilacak: list[tuple[str, str | None, str | None, str, str]] = []
    eslesen = 0
    for ad_id, metin in metinler.items():
        if ad_id in korunan:
            continue
        eslesme = urun_esle(_sade(metin), kodlar)
        if eslesme:
            urun_id, urun_adi, kod = eslesme
            yazilacak.append((ad_id, urun_id, urun_adi, "TUREV",
                              f"kreatif metninde '{kod}' geçiyor"))
            eslesen += 1
        else:
            yazilacak.append((ad_id, None, None, "YOK",
                              "kreatif metninde hiçbir ürün adı geçmiyor"))

    print(f"eşleşen: {eslesen} · ürünsüz: {len(yazilacak) - eslesen} · "
          f"kapsama: %{round(100 * eslesen / max(len(yazilacak), 1), 1)}")
    if kuru:
        print("--kuru: hiçbir şey yazılmadı")
        for satir in yazilacak[:5]:
            print("   ", satir[0], "->", satir[2] or "(yok)")
        return

    degerler = ",".join(
        "(" + ",".join(
            "NULL" if d is None else "'" + str(d).replace("'", "''") + "'"
            for d in satir) + ")"
        for satir in yazilacak)
    sql = (
        "INSERT INTO core.reklam_urun (ad_id,urun_id,urun_adi,kaynak,gerekce) "
        f"VALUES {degerler} "
        "ON CONFLICT (ad_id) DO UPDATE SET "
        "urun_id=EXCLUDED.urun_id, urun_adi=EXCLUDED.urun_adi, "
        "kaynak=EXCLUDED.kaynak, gerekce=EXCLUDED.gerekce, guncelleme=now() "
        # Bir kez daha: ELLE satırına ON CONFLICT yolundan da dokunulmaz.
        "WHERE core.reklam_urun.kaynak <> 'ELLE';"
    )
    _sorgu(sql)
    ozet = _sorgu("select kaynak||'='||count(*) from core.reklam_urun "
                  "group by kaynak order by 1;")
    print("yazıldı →", " · ".join(ozet))


if __name__ == "__main__":
    main()
