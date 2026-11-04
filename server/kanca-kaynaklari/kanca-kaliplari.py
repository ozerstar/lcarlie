#!/usr/bin/env python3
"""99 kanca kalıbı -> sınıflandırılmış, kozmetik uygunluğu işaretlenmiş JSON.

🔴 BUNLAR ÖLÇÜLMÜŞ KANCA DEĞİL, YAPI ŞABLONU. Havuzdaki diğer kancalar
piyasada gerçekten yayınlanmış ve ölçülmüş cümlelerdi (izlenme / kaç gündür
yayında). Bunlar ise doldurulacak kalıplar -- başarı verisi YOK. Aynı sütunda
gösterilirse "bu kanca tuttu" sanılır. `kaynak_tur = KALIP` ile ayrılır ve
başarı alanı BOŞ bırakılır.

🔴 KALIBIN İÇİNDEKİ YER TUTUCU RİSKİ BELİRLER. Bir şablon [süre] istiyorsa,
kozmetikte doldurulduğu anda süre iddiası olur ve mevzuat kapısına takılır --
şablonun kendisi masum görünse bile. Bu yüzden risk, kelimeye değil YER
TUTUCUYA bakarak atanır: mekanik, denetlenebilir, tartışmasız.

Kaynak: sahibin gönderdiği 99 maddelik liste (21.09.2026).
100. madde gönderilmedi (sayfa 10/10 elde yok).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KALIPLAR = [
    "Kimse bundan bahsetmiyor ama...",
    "[Meslek] camiasının sessiz kaldığı şeyi anlatacağım",
    "Herkes [gerçek] hakkında duymuştur ama kimse [acı] bilmez",
    "Bunu tesadüfen öğrendik ama...",
    "[Bunu] çok geç fark ettim, o yüzden şimdi sizinle paylaşıyorum",
    "[Konu] hakkında sana söylenenler yalan",
    "[Eylemi] yapmayı bırak",
    "[İnanç] aslında büyük bir hata",
    "[Eylemi] yapmazsan [kaynağı] kaybediyorsun",
    "İşte bu yüzden senin [nesnen] [sonucu] vermiyor",
    "[Eylem] senin [nesneni] mahvediyor",
    "[Araç/yöntem] 2026'da artık işe yaramıyor",
    "[Meslek mensupları] bunu müşterilerinden gizliyor",
    "[Konu] hakkında sana yalan söylüyorlar",
    "[Meslek mensupları] kimse görmediğinde ne yapıyor",
    "[Popüler konu] hakkındaki ve senden saklanan gerçek",
    "[Popüler şirket/araç] aslında [gerçek]",
    "Herkes [görüş] diyor. Aslında tam tersi.",
    "10 içerik üreticisinden 9'u bu hatayı yapıyor",
    "Bunu yüksek sesle söylemek ayıp sayılır ama...",
    "Çoğu insan hiç ulaşamaz",
    "Bunu görmezden gelince ne oluyor...",
    "Kimse buna dikkat etmiyor ama",
    "Bunu çok geç öğrendim",
    "[Süre] içinde [müşteri sayısı] analiz ettim — en iyilerin ortak noktası şu",
    "[Sayı] müşteriyle çalıştım ve hepsinde aynı sorun vardı: [sorun]",
    "[Sektör]de [sayı] yılın ardından tek bir şeyi anladım",
    "[Durumun] her iki tarafında da bulundum — fark şurada",
    "[Konuda] [sayı] şey inceledim — gerçekten işe yarayan tek şey bu",
    "[Durumun] içinden geçtim ve şunu çıkardım",
    "[Eylemi] değiştirdim ve [sonucu] elde ettim",
    "30 gün boyunca [eylemi] yaptım — sonuç: [sonuç]",
    "[Eylemden] vazgeçtim ve bu bana [sonucu] sağladı",
    "[İnancım] vardı — bu beni [sonuca] götürdü",
    "[İnancın] doğru olduğunu sanıyordum ama [eylemi] deneyene kadar",
    "Tesadüfen [eylemi] denedim — ve artık",
    "[Alanda] nasıl özgün olunur...",
    "[Konu] neden kolaydır — 5 neden",
    "[Konu] neden zordur — 5 neden",
    "Şu tek hatayı yapmayı bırakın",
    "Hayatını değiştirecek tek tavsiye",
    "[Konu] hakkındaki yaygın yanlış inanışlar",
    "İnsanların sana para ödemesini nasıl sağlarsın",
    "[Konu] konusunda nicelik mi nitelik mi",
    "[Alanda] daha akıllı çalışmak, daha çok değil",
    "[Konu] konusunda başarıya ulaşmam ne kadar sürdü",
    "Neden [bir şeyi] öğrenmek bu kadar uzun sürüyor",
    "[Alanda] başarılı olmak neden bu kadar zor",
    "[Niş] için 5 yapılacak ve yapılmayacak",
    "Başlarken neleri beklemeli",
    "[Niş] konusunda nefret ettiğim şey",
    "[Niş] alanındaki en kötü deneyimim",
    "[Niş] alanındaki en büyük hatam",
    "[Konu] deneyimimden çıkardığım hayat dersleri",
    "İşimde kullandığım araçlar",
    "Başlamak için paraya ihtiyacın yok",
    "[Bir şeyde] başarı abartılıyor",
    "Neden [konu] konusunda bir türlü ilerleme kaydedemiyorsun",
    "[Konu] ile başlamanın kolay yolu",
    "Başlamakta kararsızsan bunu oku",
    "Başlamak için neye ihtiyacın var",
    "[Araç] ile tanınmanın 5 yolu",
    "[Konuya] nasıl başlanır: adım adım rehber",
    "Herkesin bilmesi gereken 10 gerçek",
    "Başarıya ulaşmak için bu rehberi takip et",
    "[Konuyu] öğrenmeye nereden başlamalı...",
    "Bunun için kullandığım araçları nereden bulursun",
    "Neden sende [istenmeyen sonuç] var da [istenen sonuç] yok?",
    "Sana [provokasyon] desem ne olur?",
    "[Biri] [sonucu] nasıl elde ediyor da sen edemiyorsun?",
    "[Durumun] neden böyle olduğunu tahmin ediyor musun?",
    "[Sonucunu] neyin öldürdüğünü biliyor musun?",
    "Her gün [eylemi] yapıyorsun — işte bu yüzden [sorun] yaşıyorsun",
    "Sana 30 saniyede anlatacağım şeyi öğrenmek için [rakamı] kaybettim",
    "Sen hâlâ [eylem] yaparken, diğerleri çoktan [sonucu] elde etti",
    "Benim [süre] sürdü — peki sen bunu ne kadar sürede yaptın?",
    "[Nişte] yapılan en pahalı hata sana [rakam/kaynak] kaybettirir",
    "[Popüler tavsiyeye] inanmayı bırak — işte nedeni",
    "Utanıyorum ama hâlâ [eylemi] yapıyorum",
    "İlk [sonucum] ancak [süre] sonra geldi",
    "Bunu söylediğim için linç yiyeceğim",
    "Neden [tanınmış isim] tam olarak böyle yapıyor?",
    "[Araç]ın sana karşı çalışıyor",
    "[Bunu] yapmadan önce bir dinle",
    "Neredeyse kimsenin bilmediği [sonuç] yöntemi var",
    "Her gün [eylem] yapılırsa [süre] sonra ne olur?",
    "Bunu başlangıçta kimse anlatmadı bana",
    "Herkes [popüler tavsiye] der. Ben tam tersini yapıyorum",
    "Eğer sen [hedef kitle tanımı] isen, bu paylaşım senin için",
    "[Koşul]a sahipsen [eyleme] gerek yok",
    "Tek bir sohbet [konu]ya bakışımı değiştirdi",
    "[Beceri] için üç seviye var: hangisindeydin?",
    "DM'den soru geldi. Burada açıklıyorum",
    "Bir yıl önce [bu] oldu. Şimdi ise [değişim]",
    "Bu, [sorun]dan bıkmış olanlar için",
    "[Özelliği] olan herkesin ortak noktası ne sence?",
    "Bu tavsiye her şeyini mahvedebilir",
    "İşte insanların [eylemi] sevmesinin nedeni",
    "Hiç düşündün mü neden [ifade]?",
]

# --- RİSK KURALLARI: yer tutucuya ve kalıbın taşıdığı VAADE bakılır --------
RISK = (
    (re.compile(r"\[süre\]|30 gün|ne kadar sürdü|ne kadar sürede|"
                r"bu kadar uzun sürüyor|sonra geldi|sonra ne olur", re.I),
     "SURE_IDDIASI",
     "kozmetikte süre iddiası yasak (14 günde, 96 saatte…) — kalıp "
     "doldurulduğu anda ihlal olur"),
    (re.compile(r"\[sonu[cç]\w*\]|\[istenen sonuç\]|\[istenmeyen sonuç\]|"
                r"\[değişim\]|elde ettim|elde etti|sağladı|götürdü", re.I),
     "SONUC_VAADI",
     "kozmetik ürün sonuç vaat edemez; [sonuç] yer tutucusu doldurulduğunda "
     "etkinlik iddiası doğar"),
    (re.compile(r"\[sorun\]|\[acı\]|\[durum\w*\]|bıkmış olanlar|yaşıyorsun",
                re.I),
     "DURUM_ADI",
     "[sorun]/[durum] yer tutucusu kozmetikte hastalık ya da belirti adıyla "
     "doldurulur; hastalık hedefleyen kanca yasak"),
    (re.compile(r"\[rakam\w*\]|\[sayı\]|\[müşteri sayısı\]|10 içerik|"
                r"9'u|10 gerçek|5 neden|5 yol|üç seviye", re.I),
     "SAYI_IDDIASI",
     "rakam ispat külfeti doğurur (Ticari Reklam Yön. m.8); belgesi yoksa "
     "kullanılamaz"),
    (re.compile(r"mahvediyor|mahvedebilir|öldürdüğünü|kaybediyorsun|"
                r"kaybettirir|sana karşı çalışıyor", re.I),
     "HASAR_KORKU",
     "ürünün/durumun zarar verdiğini söylemek hasar iddiasıdır; korku "
     "kurgusu kozmetikte savunulamaz"),
    (re.compile(r"\[meslek mensupları\]|\[meslek\]|gizliyor|yalan söylüyorlar|"
                r"senden saklanan|kimse görmediğinde", re.I),
     "OTORITE_ITIBARSIZLASTIRMA",
     "hekim/eczacı gibi meslek gruplarını gizleyici gösteren kurgu; sağlık "
     "çalışanı algısı ve haksız ticari uygulama riski"),
    (re.compile(r"kimsenin bilmediği|neredeyse kimsenin|tek şey bu|"
                r"hayatını değiştirecek|başarıya ulaşmak için", re.I),
     "MUCIZE_USTUNLUK",
     "gizli/benzersiz yöntem ve 'hayatını değiştirir' kurgusu mucize ve "
     "üstünlük iddiasıdır"),
    (re.compile(r"\[popüler şirket|\[araç/yöntem\]|artık işe yaramıyor|"
                r"\[tanınmış isim\]", re.I),
     "RAKIP_KOTULEME",
     "adlandırılmış marka/ürün üzerinden karşılaştırma ve kötüleme"),
)


def sinifla(metin: str) -> dict:
    bulunan = [(ad, gerekce) for kalip, ad, gerekce in RISK if kalip.search(metin)]
    return {
        "kozmetik_uygun": not bulunan,
        "riskler": [b[0] for b in bulunan],
        "gerekce": bulunan[0][1] if bulunan else "",
    }


def main() -> int:
    hedef = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("kanca-kaliplari.json")
    cikti = {}
    for i, metin in enumerate(KALIPLAR, 1):
        cikti[metin] = dict(sinifla(metin), no=i,
                            kaynak="sahip listesi 21.09.2026")
    hedef.write_text(json.dumps(cikti, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    uygun = sum(1 for v in cikti.values() if v["kozmetik_uygun"])
    print(f"{len(cikti)} kalıp -> {hedef}")
    print(f"  kozmetikte kullanılabilir : {uygun}")
    print(f"  yapısal olarak yasak      : {len(cikti) - uygun}")
    sayac: dict[str, int] = {}
    for v in cikti.values():
        for r in v["riskler"]:
            sayac[r] = sayac.get(r, 0) + 1
    for r, n in sorted(sayac.items(), key=lambda x: -x[1]):
        print(f"    {r:<28} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
