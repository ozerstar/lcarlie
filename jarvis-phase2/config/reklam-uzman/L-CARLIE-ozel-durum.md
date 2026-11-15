# L'CARLIÉ reklam hesaplarının ölçülmüş gerçekleri (15.11.2026'ya kadar)

> Kaynak: Claude hafıza kayıtları (ölçüm tarihleri yanlarında) + 15.11.2026 canlı denetim brifi (`01 LCARLIE\META-REKLAM-BRIFI-2026-11-15.md`). Her madde ölçüm anındaki durumdur; **canlı karar vermeden önce yeniden ölç.** "Beyan" yazanlar sahip söylemidir, ölçüm değildir.

---

## 1. Hesaplar ve altyapı

- **Meta:** asıl hesap `1301171572214198` ("SAĞLIKLI YAŞAM REHBERİ" portfolyosu; ad alakasız, tuzak). Ölü hesaplar `560782561026922` (Reklam Yöneticisi varsayılan olarak bunu açar) ve `1601342818221781` (boş). Veri seti (piksel + CAPI) `2469140530193842`; eski `1922675625114734` kullanılmaz.
- `META_ADS_TOKEN` yalnız okuma. Değişiklik ancak Reklam Yöneticisi'nden elle.
- **Google:** Merchant Center `5726728276` bağlı, ek veri kaynağı 36/36 eşleşiyor, iade/kargo politikası tanımlı. Google Ads kampanyası **yok**; sahip doğrudan Google Ads hesabı açacak.
- **Ölçüm:** GTM-5XR5TQKP + GA4 G-KCPFLRG2RV canlı ama GA4 siparişlerin bir kısmını görüyor (Eylül'de 37'nin 10'u). Wix siparişlerinde UTM/fbclid/gclid **yok** (37/37). Umami (olcum.lcarlie.shop) oturum düzeyinde güvenilir kaynak. Meta pikseli pazarlama çerezi rızasına bağlı → Meta küçük bir dilimle öğreniyor.
- Pikselin satın alma hacmi: Eylül 2026'da 28 günde **34** satın alma (~8/hafta). Meta'nın ~50/hafta öğrenme eşiğinin çok altında.
- Tekrar satın alma: 29.09'da **31 müşterinin 0'ı** ikinci sipariş vermişti → LTV kredisi yok, ilk sipariş kendini ödemeli.

## 2. Ağustos–Eylül 2026: ilk reklam dönemi

- 23.08–21.09 (30 gün): harcama **27.894 TL**, gerçek sipariş **11**, net ciro **13.557 TL** → 1 TL harcamaya **0,49 TL ciro** (kâr değil ciro).
- **Harcamanın %53'ü satın alma yoluna hiç çıkmıyordu:** Instagram profiline giden reklam 7.480 TL (%26,8; 8.851 tık, Meta'nın kendi ölçümünde bile 0 satış) + WhatsApp mesajı 7.418 TL (%26,6; 26 "sonuç" = konuşma, gelir 0). Mağazaya giden (SHOP_NOW) 12.175 TL (%43,6) o sırada kapalıydı.
- Meta 30 günde 48 satış / 34.194 TL iddia ediyordu; defterde 11 / 13.557 TL → **4,4 kat şişik**.
- Mağaza sayfası dönüşümü: 5.247 tık → ≤11 sipariş = **%0,21** (sektör sık anılan %1–2; kaynaksız kıyas).
- Dönem kıyası: reklamsız 06.02–31.07 aylık 3,9 sipariş / 6.648 TL; reklamlı 11.08–12.09 aylık 12,7 sipariş / 26.719 TL. Reklam döneminin tamamı: ciro 29.390 TL, harcama 36.947 TL → **−7.556 TL** (ürün maliyeti hariç; ödemelerin %43'ü çevrim dışı ve elle satışlar Wix'te yoktu → kesin değil).
- 24–26.09: tüm kampanyalar kapalı, harcama sıfır. "Satış durdu" alarmlarının sebebi talep değil musluğun kapalı olmasıydı; ayrıca 4 kapıda ödemeli VIREON satışı (4.800 TL) ciro sayacına girmiyordu.
- Önceki dönem dersi: Meta'da yalnız 1 hafta, yalnız VIREON (katalogdaki mevzuat açısından en zor ürün) denenmişti; "Meta çalışmıyor" sonucu o testten çıkarılamaz. 7 aylık 72.223 TL cironun neredeyse tamamı reklamsız (organik + WhatsApp) gelmişti.

## 3. KINESIS+ Keşif Dalga 1 (30.09–Ekim 2026)

- 3 set × 100 TL/gün → sonra 540 TL/gün/set, aynı kitle, kreatif ekseni testi (ABO), Sepete Ekle optimizasyonu (satın alma hacmi yetersiz).
- 30 günlük sonuç sütunu (11.10): **AS1 Bileşim-Premium 716 sepete ekleme, 8,07 TL/adet** (5.780 TL); AS2 Aktif-Spor 26 / 223,93 TL; AS3 Yoğun-Tempo 19 / 306,54 TL. AS2 ve AS3 kapatıldı. CTR/TBM'ye bakılıp AS1'in kapatılması önerilmişti — **yanlıştı**; sonuç sütunu okunmadan karar verilmez.
- **Ama 759 sepete eklemenin Wix'te karşılığı yoktu**: son 30 günde gerçek müşteri siparişi 0, kampanyadan 0 checkout. Kök neden: reklam → ara sayfa → "Sepete ekle" → Wix sepet köprüsü ortanca **5,6 sn** bekletiyor, ortanca oturum **5,26 sn**; %66'sı 8 sn'den önce çıkıyor, /cart → /checkout %1,2. Meta'nın sepete eklemesi düğmeye basılınca ateşlenen piksel olayıydı.
- Yaratıcı bulgu: durağan açılış TBM'yi 0,79 → 4,98 TL'ye çıkardı; ölçülen sıklık tavanı 2,0–2,2 (maks 3,2); linksiz reklam bağlantı CTR %10,9, SHOP_NOW %5,0; müşteri soruları fiyat %55, içerik %54.
- Kategori fiyat gerçeği: "masaj kremi" rafı 35–568 TL, KINESIS+ 1.950 TL → kategori dili bırakıldı (sporcu kremi / yoğun tempo sonrası bakım). İçeride 5 ürün aynı bölgede yarışıyor (KINESIS+, DORSIVIA, DERMARNICA, DERMAMOVERA, DERMAVASC).
- Terk edilmiş 3–4 VIREON checkout'u (12–17.09) hiç aranmamıştı → sıcak müşteri geri kazanımı reklamdan ucuz.

## 4. 11.11 kampanyası (09.11–18.11) ve Trendyol'a trafik

- Tüm platformlarda %30 (sahip, zararına satılan 900 TL bandı bilerek kabul edildi). Trendyol'da ayrıca Plus %20, kozmetik kuponları, Plus kuponlar, Trendyol karşılamalı kupon — **üst üste biniyor**.
- **Meta "11.11 | Trendyol LEMOS | Trafik"** (kendi hesap → Trendyol ürün linki, pikselsiz):
  - 13.11 ölçümü: harcamanın **%98,9'u** (2.183 TL'nin) ve 3.372 tıklamanın **3.365'i Audience Network**'e gitti; Instagram/Facebook'tan 7 tık. Yerleşim otomatik bırakılmıştı. Reklam bazında yüksek CTR'ler (DERMANOVA %11, HYDRAVIE %14) **AN gürültüsü**, kreatif sinyali değil.
  - 13.11 akşam tüm setler yalnız Instagram'a alındı (sahip: "Facebook'u boşver"); 14.11'de AN = 0 doğrulandı.
  - 15.11 15:17 toplam: **4.049,79 TL, 5.661 bağlantı tıklaması**; setlerin 3'ü Bağlantı Tıklaması, 1'i LPV optimizasyonu.
- **Meta "UGC Tanıtıcı | 4 Ürün | Trendyol Satış"**: adı satış ama 4 setin optimizasyonu **LPV**. 15.11: **2.890,39 TL, 1.748 tık**. Kanca bulgusu: "Erkekler!" bağlantı CTR %3,2, LUCIDERM "Yıkadıktan bir saat sonra yine parlıyor mu?" %2,6, diğerleri %2,0–2,3 (az örneklem). 480×854 videolar Instagram'a alınınca "Medya yeterince geniş değil" ile durdu → 1080×1920'ye büyütüldü.
- **İki kampanya toplamı ~6.940 TL** harcamaya karşı izlenen ürünlerde **4 Trendyol siparişi / 2.491,28 TL** (ödenen fiyat). Aynı 4 sipariş iki raporda görünüyor, toplanmaz; atıf değil, örtüşme. 12.11'deki 5 Trendyol siparişinin **3'ü aynı Ankaralı alıcı** (3 dakika içinde). 13–14–15.11 genel Trendyol siparişi 0 (sipariş nöbetçisi canlı, ölçüm hatası değil). Kaba MER ≈ 0,36.
- Liste fiyatı tuzağı: Trendyol `amount` üstü çizili fiyat → kampanya-izle önce ciroyu 5.126 TL ve ROAS 2,97 gösterdi; gerçek 2.491 TL / 1,42 (o andaki harcamayla). `startDate` filtresi kargo tarihine göre süzüp sahte ROAS 7,51 de üretmişti.
- **Trendyol panel Meta** "11.11 Meta Yeniden Hedefleme 2" (12–18.11, 2.800 TL): 14.11'de 747 TL, 127 tık, **0 satış**.
- **Trendyol ürün reklamı:** 23.10'dan beri 1 aktif, 838 gösterim / 7 tık / 0 satış / 28,60 TL (10.11).
- **Komisyonlu influencer:** eski 3 reklamda (%50 ve %20 dahil) **paylaşım 0**. 11.11 için %60 açıldı (sahip bilerek). Sonuç bu belge tarihinde ölçülmedi.
- Trendyol reklam bakiyesi: 10.347 TL (10.11) → 4.776 TL (14.11) + 18.11 iadesi beklenir.
- Hazır ama hiç yüklenmemiş kreatif: `LCARLIE-11-11-EDITORIAL-V2` içinde 7 ürün + 3 KINESIS alternatifi = **10 kaydırmalı set**. Sahip: "kaydırmalı istemiştim, hiç görmedim".
- En iyi insansız kreatif örneği: "Formülü oku, farkı gör. Premium olan ambalaj değil, içindekidir." bağlantı CTR %27, 0,46 TL/tık (diğerleri %6–8). ⚠️ Yerleşim kırılımı bu reklam için ayrıca okunmadı; AN döneminden ise şişik olabilir.

## 5. Efsane Günler hazırlığı (18–29.11)

- Sahip: "her şey 18'inde başlasın, reklamlar dahil". Kendi kanallar %20 sepette (Wix kural 18.11 21:00Z → 29.11), Trendyol "Efsane öncesi %20" 18–21.11, sonra Efsane kademe fiyatı 22.11 08:00–29.11 08:00 (32 ürün Avantajlı kademe; azami fiyatlar liste fiyatının %19–52 altında + sepette %5). BRIGHT SMILE ve EASYCOMB Efsane kademesinde dışarıda (Avantajlıda eksi). Idefix %20 sepette 18–29.11. n11 şemsiyeler 30.11'e kadar. HB %20 kurulamadı (oturum).
- Meta: kendi hesap **500 TL/gün**; Trendyol panel Meta **19–28.11, 4.000 TL** (planlandı, 19.11 sabahı oluşturulacak).
- **18.11'de yapılacak:** Plus %20 + Plus kuponlar + kozmetik kuponlardan çık (yoksa Efsane fiyatının üstüne iner; HYDRAVIE katkısı ~185 → ~50 TL). 19.11: Wix "11.11 · %30 İNDİRİM" ürün etiketini kaldır, eski etiketleri geri koy.
- Kreatif: V1 (ürünsüz fon + ürün dizisi) **sahip reddetti** ("hook yok, beni içine almıyor"). V2-KANCALI: 9 sahne × post/story/kare = 27 görsel, Türk insan + an + ürün, etiket birebir, rakamsız teklif metni.
- 15.11 brifindeki karar: 27 dosya tek seferde açılmaz; gerçekten farklı 4–5 kavram seçilip ölçülür.

## 6. Marj ve maliyet gerçeği

- **Maliyetin tek kaynağı finans merkezi (sahip 15.11.2026).** Jarvis Finans > Ürün Kârlılığı: üretim faturası + tester/TTS/ÜGR/reklam materyali payı (ürünlere eşit) ÷ üretilen adet = birim tam maliyet, KDV hariç. Eski 400 TL ELLE beyanı, "120 TL" ve "100 TL duyarlılık" senaryoları geçersiz (veritabanında iptal edildi, silinmedi). Wix Maliyet alanı bunun ×1,20 KOPYASI (36/36 tutarlı, 15.11 ölçüldü).
- **Oku:** `ssh lcarlie "docker exec lcarlie-postgres psql -U n8n -d n8n -c \"SELECT urun_kod, birim_maliyet_kdv_haric, birim_maliyet_kdv_dahil, durum, finans_son_kontrol FROM core.urun_maliyet_guncel WHERE urun_turu='KOZMETIK' ORDER BY urun_kod\""` — saatlik tazelenir; `durum=VERI_YOK` → maliyet yok (0 değil). Aşağıdaki tablo 15.11 16:17 anlığıdır, **kopyadır**; karar öncesi sorguyla teyit et.
- Hesap: K = P/1,20 − komisyon − maliyet(KDV hariç) − kargo 92,66 (KDV hariç); başabaş ROAS = P/K. Wix'te komisyon = POS %5 (`core.maliyet_bileseni`); Trendyol'da ürünün `core.urun_platform_komisyon` oranı (* = kayıt yok, %19 varsayıldı). Fiyatlar 15.11 Wix liste / Trendyol satış fiyatı (11.11 kampanyası sürüyor). "Eski 400" sütunu = aynı Wix fiyatı ve POS ile 400 TL beyanının verdiği eşik.

| Ürün | Maliyet KDV hariç | Maliyet KDV dahil | Wix fiyat | Wix katkı K | Wix başabaş ROAS | (eski 400 ile) | Trendyol fiyat | TY kom. | TY katkı K | TY başabaş ROAS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BABY RESCUE | 67,62 | 81,14 | 900,00 | 544,72 | **1,65** | 4,24 | 1.035,00 | %20 | 495,22 | **2,09** |
| BABYDENT | 90,44 | 108,53 | 1.100,00 | 678,57 | **1,62** | 2,98 | 1.265,00 | %20 | 618,07 | **2,05** |
| BABYSHOWER | 95,02 | 114,02 | 1.100,00 | 673,99 | **1,63** | 2,98 | 1.465,00 | %20 | 740,15 | **1,98** |
| BABYSOFT | 90,58 | 108,70 | 2.100,00 | 1.461,76 | **1,44** | 1,82 | 2.280,00 | %20 | 1.260,76 | **1,81** |
| BABYSOL | 115,44 | 138,53 | 1.250,00 | 771,07 | **1,62** | 2,57 | 1.450,00 | %20 | 710,23 | **2,04** |
| BRIGHT SMILE | 92,69 | 111,23 | 950,00 | 558,82 | **1,70** | 3,78 | 869,00 | %19 | 373,71 | **2,33** |
| BUGUARD | 75,16 | 90,19 | 900,00 | 537,18 | **1,68** | 4,24 | 1.093,00 | %19* | 535,34 | **2,04** |
| CALJAW | 81,30 | 97,56 | 1.100,00 | 687,71 | **1,60** | 2,98 | 1.265,00 | %19 | 639,86 | **1,98** |
| CALMAROS | 79,08 | 94,90 | 1.850,00 | 1.277,43 | **1,45** | 1,93 | 2.427,00 | %19 | 1.389,63 | **1,75** |
| CALMORIS | 81,60 | 97,92 | 1.100,00 | 687,41 | **1,60** | 2,98 | 1.480,00 | %19 | 777,87 | **1,90** |
| DERMABED | 84,88 | 101,86 | 1.950,00 | 1.349,96 | **1,44** | 1,88 | 2.487,00 | %19 | 1.422,43 | **1,75** |
| DERMACORN | 79,88 | 95,86 | 900,00 | 532,46 | **1,69** | 4,24 | 1.237,00 | %19 | 623,26 | **1,98** |
| DERMAGUARD | 95,02 | 114,02 | 1.200,00 | 752,32 | **1,60** | 2,68 | 1.485,00 | %19 | 767,67 | **1,93** |
| DERMAMOVERA | 82,23 | 98,68 | 1.950,00 | 1.352,61 | **1,44** | 1,88 | 2.242,00 | %19 | 1.267,46 | **1,77** |
| DERMANOVA | 90,30 | 108,36 | 2.100,00 | 1.462,04 | **1,44** | 1,82 | 2.685,00 | %19 | 1.544,39 | **1,74** |
| DERMARNICA | 73,69 | 88,43 | 2.100,00 | 1.478,65 | **1,42** | 1,82 | 2.658,00 | %19 | 1.543,63 | **1,72** |
| DERMASTRA | 79,88 | 95,86 | 2.100,00 | 1.472,46 | **1,43** | 1,82 | 2.280,00 | %19 | 1.294,26 | **1,76** |
| DERMAVASC | 88,82 | 106,58 | 2.100,00 | 1.463,52 | **1,43** | 1,82 | 2.686,00 | %19 | 1.546,51 | **1,74** |
| DORSIVIA | 80,02 | 96,02 | 2.100,00 | 1.472,32 | **1,43** | 1,82 | — | %19 | — | — |
| EASYCOMB | 80,02 | 96,02 | 1.020,00 | 626,32 | **1,63** | 3,33 | 1.127,00 | %19 | 552,36 | **2,04** |
| FEMISIA | 89,88 | 107,86 | 2.400,00 | 1.697,46 | **1,41** | 1,73 | 2.760,00 | %19 | 1.593,06 | **1,73** |
| HAIR NOURISHER | 83,82 | 100,58 | 1.200,00 | 763,52 | **1,57** | 2,68 | 1.285,00 | %19 | 650,20 | **1,98** |
| HYDRAVIE | 94,88 | 113,86 | 1.200,00 | 752,46 | **1,59** | 2,68 | 1.497,00 | %19 | 775,53 | **1,93** |
| INTIMBLANC | 80,16 | 96,19 | 2.100,00 | 1.472,18 | **1,43** | 1,82 | 2.678,00 | %19 | 1.550,03 | **1,73** |
| KINESIS+ | 87,06 | 104,47 | 1.950,00 | 1.347,78 | **1,45** | 1,88 | 2.457,00 | %19 | 1.400,95 | **1,75** |
| LIFTELLE | 78,95 | 94,74 | 2.100,00 | 1.473,39 | **1,43** | 1,82 | 2.680,00 | %19 | 1.552,52 | **1,73** |
| LIPVORA | 62,97 | 75,56 | 900,00 | 549,37 | **1,64** | 4,24 | 1.135,00 | %19 | 574,55 | **1,98** |
| LUCIDERM | 80,02 | 96,02 | 1.200,00 | 767,32 | **1,56** | 2,68 | 1.247,00 | %19 | 629,56 | **1,98** |
| MENTHALIS | 77,70 | 93,24 | 1.100,00 | 691,31 | **1,59** | 2,98 | 1.480,00 | %19 | 781,77 | **1,89** |
| MINISOOTH | 85,02 | 102,02 | 1.200,00 | 762,32 | **1,57** | 2,68 | 1.349,00 | %20 | 676,69 | **1,99** |
| OPTYWAVE | 89,47 | 107,36 | 1.100,00 | 679,54 | **1,62** | 2,98 | 1.265,00 | %19* | 631,69 | **2,00** |
| ORAGARDE | 75,58 | 90,70 | 900,00 | 536,76 | **1,68** | 4,24 | 1.237,00 | %19 | 627,56 | **1,97** |
| SERALIMBO | 85,30 | 102,36 | 2.100,00 | 1.467,04 | **1,43** | 1,82 | 2.280,00 | %19 | 1.288,84 | **1,77** |
| SOFTGUARD | 79,88 | 95,86 | 950,00 | 571,63 | **1,66** | 3,78 | — | %17 | — | — |
| SUNACNEA | 104,88 | 125,86 | 1.200,00 | 742,46 | **1,62** | 2,68 | 1.280,00 | %19 | 625,93 | **2,04** |
| VIREON | 90,30 | 108,36 | 2.400,00 | 1.697,04 | **1,41** | 1,73 | 2.760,00 | %19 | 1.592,64 | **1,73** |

- Okuma: gerçek maliyet ürün başına 63–115 TL KDV hariç; 400 TL beyanının **~%22'si**. Başabaş ROAS Wix'te 1,41–1,70, Trendyol'da 1,72–2,33 bandına indi (eski: Wix 1,73–4,24). Bu, reklamın kârlı olduğunu göstermez — ölçülen MER/defter hâlâ esastır (Bölüm 2–3: reklam dönemi −7.556 TL, 11.11 harcama ~6.940 TL / TY ciro 2.491 TL).
- DORSIVIA ve SOFTGUARD'da Trendyol satış fiyatı ham veride yok/0 → TY eşiği hesaplanmadı. BUGUARD: Trendyol'daki 8684869609301 ilanının başlığı SOFTGUARD (ÜTS'de 9301 = BUGUARD) — ilan/barkod teyidi gerekir.
- `ecommerce_profitability` kirli: Haziran–Temmuz'daki ölü %70 indirim LUCIDERM, EASYCOMB, BRIGHT SMILE, BABYSOL'ü eksi gösteriyor. Bugünkü kendi site indirim tavanı (kampanya dışı) %15.
- Komisyon: Trendyol ort. %19,1 (%17–20), Idefix %10 (BABYSHOWER %15). Kargo 92,66 TL KDV hariç (Sürat). Idefix'te 30 üründe zarar eden yok, ortalama katkı ~%49 (23.10'da 400 TL beyanla; gerçek maliyetle daha yüksek).
- Trendyol'da 900 TL bandı %20+ indirimde reklamsız bile zarar; 11.11 %30'da eksi (sahip kabul etti).
- Wix ile Trendyol fiyatı farklı (ör. KINESIS+ 1.950 / 2.457 TL); reklam fiyat referansı kendi kanalının fiyatıdır.

## 7. Platform ve hesap tuzakları (tekrar edilmiş hatalar)

1. Advantage+ kreatif yapay zekâsı varsayılan açık; yasak iddia ve bozuk Türkçe üretti. Çoğaltma kapattıklarını geri açıyor.
2. Trendyol linkiyle LPV optimizasyonu yayında #1634013 hatasıyla reddediliyor → Bağlantı Tıklaması.
3. Yeni reklamda tarayıcı eklentisi (WhatsApp/Messenger), katalog ürün etiketleri, koleksiyon/döngü katalog ürünleri, görsel rötuşları, "detayları zaman içinde göster" varsayılan açık.
4. "Hariç tutulan yerlerde sınırlı harcama" platform değişince kendiliğinden işaretleniyor.
5. CTA `call_to_action_type` Advantage+ kreatiflerde boş gelir; `asset_feed_spec` içinden okunur.
6. Hesap borcu varsa "Yayınla" ödeme penceresi açar.
7. Ads Manager kırılımı seçili tarih aralığıdır; "şu an" sorusunda yalnız bugün.
8. Panel/izleme betiği eşiği ile gerçek iş sonucu farklı şeyler: alarm metni kümülatif sayıyı "devam ediyor" gibi sunmamalı.

## 8. Açık sorular (ölçülmesi gereken, karar öncesi)

1. ~~Gerçek ürün maliyeti~~ → **ÇÖZÜLDÜ 15.11.2026**: finans merkezi (`core.urun_maliyet_guncel`). Kalan açık: birim maliyet tüm üretimin ortalaması ve genel gider ürünlere eşit dağıtılıyor; parti/dağıtım anahtarı değişirse birim maliyet değişir (saatlik aktarım yakalar).
2. 11.11 komisyonlu influencer: paylaşım ve satış geldi mi, ödenecek tutar.
3. Efsane Günler süresince kendi hesap → Trendyol trafiğinin Instagram-only performansı (eşik: ~1.000 IG tıkında ≥1–2 sipariş; tutmazsa 11.11 Trafik bütçesi yarıya + UGC FEMISIA/HYDRAVIE setleri kapat — onayla).
4. Kendi siteye dönüş: Wix ürün sayfası dönüşümü (%0,21 ölçülmüştü) düzelmeden siteye ücretli trafik verimli mi?
5. Wix teşekkür sayfası anketi ve UTM şeması (atıf yokluğunun ucuz çaresi).
6. Google Ads hesabı + dönüşüm etiketi.
7. Jarvis'te `META_MEDIA` ve `MARKETPLACE` departmanlarının sorumlusu tanımlı değil (22.09 notu) → bu ikili o boşluğa önerilebilir; atama sahibin ticari kararı.
