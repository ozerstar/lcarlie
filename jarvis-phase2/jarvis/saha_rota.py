"""Saha rotası: bir başlangıç noktasından yürüyüş sırası çıkarır.

Sahibin tarifi: *"metro istasyonundan başlayacak şekilde, 20-50 metre arayla
en yakın satış potansiyelli yerleri hazırlayacağız."*

## Üç kusur ve çözümleri (prototipte ÖLÇÜLDÜ)

**1. Aynı yer iki kayıt.** OSM'de bazı işletmeler hem nokta hem alan olarak
bulunuyor. Prototipte "Reyhan Eczanesi" 5 metre arayla iki kez çıktı, aynı
telefonla. Ayıklanmazsa saha elemanı aynı kapıyı iki kez çalar.
→ Aynı ada sahip ve `KOPYA_ESIGI_M` içindeki ikinci kayıt atlanır.

**2. Açgözlü sıralama miyop.** "Hep en yakına git" kuralı sokağın sonunda
karşı mahalleye zıplatıyor: prototipte 15 durak için 13,5 km çıktı.
→ Açgözlü ile başlanır, sonra **2-opt** ile kesişen bacaklar düzeltilir.
Bu bir optimum garantisi vermez; ölçülebilir bir iyileşme verir ve rapor
edilir -- "en iyi rota" demek, ispatlanmamış bir iddia olurdu.

**3. Başlangıç noktası rastgele seçilemez.** Prototipte ilk durağa 11 km
yürünüyordu çünkü istasyonu ben listeden ilk geleni aldım.
→ Başlangıç ya çağıran tarafından verilir ya da hedef kümesinin
ağırlık merkezine EN YAKIN aday seçilir.

## Mesafe

Haversine (kuş uçuşu) kullanılır. Gerçek yürüyüş mesafesi değildir ve öyle
sunulmaz; yoğun şehir dokusunda sıralama için yeterlidir. Gerçek yürüyüş
mesafesi istenirse bir yönlendirme sunucusu (OSRM) gerekir -- o ayrı bir
altyapı kararıdır, bu modül onu VARSAYMAZ.
"""
from __future__ import annotations

import math

# Bu mesafedeki aynı adlı iki kayıt tek işletme sayılır. 25 m, bir binanın
# iki kapısını ayırmayacak kadar küçük, komşu iki eczaneyi birleştirmeyecek
# kadar büyük olsun diye seçildi.
KOPYA_ESIGI_M = 25.0

# 2-opt'un tur sayısı tavanı: rota uzunluğu kadar değil, sabit. Saha listesi
# 100 durağı geçmiyor; sınırsız döngü, kazancı olmayan yerde zaman yakar.
IYILESTIRME_TURU = 40


def mesafe_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """İki koordinat arası kuş uçuşu mesafe (metre)."""
    yaricap = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * yaricap * math.asin(math.sqrt(h))


def _ad(n: dict) -> str:
    return (n.get("ad") or "").strip().casefold()


def kopyalari_ayikla(noktalar: list[dict]) -> tuple[list[dict], int]:
    """Aynı adlı ve çok yakın kayıtları teke indirir.

    Adsız kayıtlar ASLA birleştirilmez: adı olmayan iki nokta aynı yer
    olabilir de olmayabilir de, ve bunu bilmiyoruz. Bilmediğimiz için
    silmek, veriyi kaybetmenin en sessiz yoludur.
    """
    tutulan: list[dict] = []
    atilan = 0
    for n in noktalar:
        ad = _ad(n)
        if ad:
            kopya = any(
                _ad(t) == ad
                and mesafe_m((n["enlem"], n["boylam"]), (t["enlem"], t["boylam"]))
                <= KOPYA_ESIGI_M
                for t in tutulan)
            if kopya:
                atilan += 1
                continue
        tutulan.append(n)
    return tutulan, atilan


def _uzunluk(sira: list[dict], baslangic: tuple[float, float]) -> float:
    toplam = 0.0
    simdi = baslangic
    for n in sira:
        hedef = (n["enlem"], n["boylam"])
        toplam += mesafe_m(simdi, hedef)
        simdi = hedef
    return toplam


def _acgozlu(noktalar: list[dict], baslangic: tuple[float, float]) -> list[dict]:
    kalan = list(noktalar)
    sira: list[dict] = []
    simdi = baslangic
    while kalan:
        kalan.sort(key=lambda n: mesafe_m(simdi, (n["enlem"], n["boylam"])))
        n = kalan.pop(0)
        sira.append(n)
        simdi = (n["enlem"], n["boylam"])
    return sira


def _iki_opt(sira: list[dict], baslangic: tuple[float, float]) -> list[dict]:
    """Kesişen bacakları ters çevirerek kısaltır. Kazanç yoksa dokunmaz."""
    en_iyi = list(sira)
    en_iyi_uzunluk = _uzunluk(en_iyi, baslangic)
    for _ in range(IYILESTIRME_TURU):
        gelisti = False
        for i in range(len(en_iyi) - 1):
            for j in range(i + 2, len(en_iyi)):
                aday = en_iyi[:i + 1] + en_iyi[i + 1:j + 1][::-1] + en_iyi[j + 1:]
                aday_uzunluk = _uzunluk(aday, baslangic)
                if aday_uzunluk + 0.5 < en_iyi_uzunluk:
                    en_iyi, en_iyi_uzunluk = aday, aday_uzunluk
                    gelisti = True
        if not gelisti:
            break
    return en_iyi


def rota_kur(baslangic: tuple[float, float], noktalar: list[dict],
             en_fazla_durak: int = 25) -> dict:
    """Yürüyüş sırası üretir.

    Dönen sözlükte `iyilesme_m` var: açgözlü sıralamaya göre ne kadar
    kısaldığı. Bu sayı raporlanır çünkü "en iyi rota" demek ispatlanmamış
    bir iddia olurdu; "şu kadar kısalttı" ölçülebilir bir gerçektir.
    """
    temiz, kopya = kopyalari_ayikla(noktalar)
    if not temiz:
        return {"durum": "HEDEF_YOK", "duraklar": [], "toplam_m": 0.0,
                "kopya_ayiklanan": kopya, "iyilesme_m": 0.0}

    secilen = _acgozlu(temiz, baslangic)[:en_fazla_durak]
    ham_uzunluk = _uzunluk(secilen, baslangic)
    iyilestirilmis = _iki_opt(secilen, baslangic)
    son_uzunluk = _uzunluk(iyilestirilmis, baslangic)

    duraklar = []
    simdi = baslangic
    for sira_no, n in enumerate(iyilestirilmis, 1):
        hedef = (n["enlem"], n["boylam"])
        adim = mesafe_m(simdi, hedef)
        kayit = dict(n)
        kayit["sira"] = sira_no
        kayit["onceki_mesafe_m"] = round(adim, 1)
        duraklar.append(kayit)
        simdi = hedef

    return {
        "durum": "HAZIR",
        "duraklar": duraklar,
        "toplam_m": round(son_uzunluk, 1),
        "kopya_ayiklanan": kopya,
        "iyilesme_m": round(ham_uzunluk - son_uzunluk, 1),
        "aday_sayisi": len(temiz),
    }


def baslangic_sec(adaylar: list[dict], hedefler: list[dict]) -> dict | None:
    """Hedef kümesinin ağırlık merkezine en yakın adayı seçer.

    Prototipte listedeki ilk istasyon alınmıştı ve ilk durağa 11 km
    yürünüyordu. Başlangıç, gidilecek yerlere yakın olmalı.
    """
    if not adaylar or not hedefler:
        return None
    orta = (sum(h["enlem"] for h in hedefler) / len(hedefler),
            sum(h["boylam"] for h in hedefler) / len(hedefler))
    return min(adaylar, key=lambda a: mesafe_m(orta, (a["enlem"], a["boylam"])))
