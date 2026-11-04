"""TİTCK sağlık beyanı ön taraması (kozmetik için).

Bu bir ön filtredir, hukuki inceleme değildir. YASAK = kozmetikte kullanılamaz,
DİKKAT = kanıt/dosya gerektirir veya bağlama göre risklidir.
"""
import re

from .util import katla

KURALLAR = [
    # (desen, seviye, açıklama)
    (r"tedavi (eder|edici|sağlar|etmek)|tedavisi|tedavi\b", "YASAK", "Tedavi iddiası kozmetikte kullanılamaz"),
    (r"iyileştir|iyileşme sağlar|iyileşmesini", "YASAK", "İyileştirme iddiası"),
    (r"şifa|şifalı", "YASAK", "Şifa iddiası"),
    (r"\bgeçirir\b|geçirmeye yardım|ortadan kaldırır|yok eder", "YASAK", "Hastalık/sorun giderme iddiası"),
    (r"ilaç gibi|ilaç etkisi|ilaçsız tedavi", "YASAK", "İlaç benzetmesi"),
    (r"mucize|kesin çözüm|kalıcı çözüm|garantili|%100 etkili|yüzde yüz etkili", "YASAK", "Abartılı/kesin sonuç vaadi"),
    (r"yan etkisi(z| yok)", "YASAK", "Yan etkisiz iddiası"),
    (r"egzama|sedef|hemoroid|basur|varis|kanser|enfeksiyon|iltihap|mantar (tedavi|hastal)|akne tedavi|dermatit|rozase tedavi",
     "YASAK", "Hastalık adı ile ilişkilendirme"),
    (r"ağrı(yı)? (keser|giderir|geçirir)|ağrı kesici", "YASAK", "Ağrı giderme iddiası"),
    (r"saç dökülmesini (durdurur|önler)|tüy dökülmesini durdurur", "YASAK", "Tıbbi sonuç iddiası"),
    (r"antibakteriyel|antiseptik|antiviral|anti-?inflamatuvar|mikrop öldür", "DİKKAT", "Biyosidal/tıbbi çağrışım, kanıt gerekir"),
    (r"doktor önerisi|doktor onaylı|dermatolog onaylı|hekim önerisi|eczacı önerisi", "DİKKAT", "Meslek mensubu önerisi kanıt ve izin gerektirir"),
    (r"klinik olarak kanıtlanmış|bilimsel olarak kanıtlanmış|klinik test", "DİKKAT", "Ürün dosyasında kanıt bulunmalı"),
    (r"zararsız|en iyi\b|bir numara|rakipsiz", "DİKKAT", "Mutlak/karşılaştırmalı ifade"),
    # 29.10.2026 eklendi: ürün adlarında / eski fiyat listesinde geçen ve filtreden "UYGUN" çıkan ifadeler.
    (r"önler\b|önleyici|önlemeye|engeller\b", "DİKKAT", "Önleme iddiası kanıt gerektirir"),
    (r"\bgiderir\b|giderici", "DİKKAT", "Giderme iddiası kanıt gerektirir"),
    (r"lifting|sıkılaştır|toparlayıcı etki", "DİKKAT", "Fiziksel sonuç iddiası kanıt gerektirir"),
    (r"selülit|çatlak|pişik|eklem|kemik", "DİKKAT", "Sağlık durumu çağrışımı; bağlamı kontrol et"),
    (r"yaşlanmayı (durdurur|geciktirir|önler)|anti-?aging|kırışıklığı (giderir|yok eder)", "DİKKAT",
     "Yaşlanma karşıtı sonuç iddiası"),
    (r"beyazlatır|beyazlatıcı|leke(leri)? (açar|giderir|siler)", "DİKKAT", "Beyazlatma/leke iddiası kanıt gerektirir"),
]

# Desen ve metin aynı katlamadan geçer: büyük harfli 'KLINIK OLARAK' da yakalanır.
_COMPILED = [(re.compile(katla(p)), lvl, msg) for p, lvl, msg in KURALLAR]


def check(text):
    t = katla(text)
    hits = []
    for rx, lvl, msg in _COMPILED:
        for m in rx.finditer(t):
            hits.append({"seviye": lvl, "ifade": m.group(0), "neden": msg})
    durum = "YASAK" if any(h["seviye"] == "YASAK" for h in hits) else ("DİKKAT" if hits else "UYGUN")
    return {"durum": durum, "bulgular": hits}
