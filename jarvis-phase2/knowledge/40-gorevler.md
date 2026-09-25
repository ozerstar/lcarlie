---
konu: Katalog, saha ve sosyal medya için günlük/haftalık/aylık görevler
anahtar: [gorev, görev, gunluk, günlük, haftalik, haftalık, aylik, aylık, katalog, saha, instagram, zamanlayici, zamanlayıcı, takvim, rutin]
gizlilik: ic-bilgi
kaynak: /etc/systemd/system/lcarlie-*.timer (ölçülmüş, systemctl list-timers)
uretim: elle yazıldı 25.09.2026
---

# Görev takvimi — katalog, saha, sosyal medya

Bu dosya **ne zaman ne olduğunu** söyler. Her satırın karşılığı çalışan bir
systemd zamanlayıcısıdır; "yapılacak" listesi değil, **yapılanın kaydı**.

🔴 **ÜRETİLEN HİÇBİR ŞEY KENDİLİĞİNDEN YAYINLANMAZ.** Dış eylem kapalı
(`EXTERNAL_ACTIONS=false`). Jarvis hazırlar, sahip panelden onaylar.

---

## GÜNLÜK

| Saat | İş | Neden günlük | Zamanlayıcı |
|---|---|---|---|
| 05:20 | **Katalog üretimi** — 36 ürünün metni yayındaki Wix açıklamasından yeniden çıkarılır, her cümle mevzuat denetçisinden geçer | Wix metni elle düzeltilebiliyor (güneş kremlerindeki zorunlu ibare eksikliği gibi). Katalog o düzeltmeyi bir gün içinde almalı; haftalık olsaydı eczaneye eski metin götürülürdü | `lcarlie-katalog-uret` |
| 07:45 | Güncel olaylar bülteni | mevcut | `lcarlie-guncel-olaylar` |
| 08:17 | Yönetici brifingi | mevcut | `lcarlie-executive-brief` |
| 08:30 | Tasarım nöbeti | mevcut | `lcarlie-tasarim-nobet` |
| 06:20 | Sayfa ölçümü | mevcut | `lcarlie-sayfa-olcum` |

**Günlük, insan tarafı (zamanlayıcı yok — karar gerektirir):**
1. `KATALOG` sekmesindeki uyarı satırını oku. Eksik INCI, eksik bayi
   fiyatı ve barkod çakışması orada yazar.
2. `INSTAGRAM PLANI` bölümünde karar bekleyen paket varsa onayla ya da
   reddet. Karar verilmeyen paket yeni paket üretilmesini **engeller** —
   bu bilerek böyle: yığılmış liste okunmaz.
3. `SAHA` sekmesinde o gün gidilecek rotayı çıkar.

---

## HAFTALIK

| Gün | İş | Neden haftalık | Zamanlayıcı |
|---|---|---|---|
| Pazartesi 06:10 | **Instagram gönderi paketleri** — ölçülmüş veriden (124 gönderi etkileşimi + 63 reklam kreatifi maliyeti + gerçek satış sinyali) yeni paketler | Paket üretmek bedava, **karar vermek** değil. Günlük koşsaydı sahip 7 günde 49 paketle karşılaşır ve hiçbirine bakmazdı | `lcarlie-ig-gonderi` |
| Cumartesi 10:11 | Kreatif hattı | mevcut | `lcarlie-kreatif-hat` |

**Haftalık, insan tarafı:**
1. Onaylanan gönderiyi çek/tasarla ve yayınla, sonra panelde
   `YAYINLANDI` işaretle. İşaretlenmeyen paket "onaylandı ama yapılmadı"
   olarak durur — bu ayrım kasten var.
2. Saha ziyaretlerinde girilen notları gözden geçir
   (`mart.katalog_ilgi`): hangi ürün ilgi görüyor, hangisi görmüyor.
3. Bayi fiyatı girilmemiş ürün kaldıysa karar ver. Katalog o ürünü "—"
   ile gösteriyor ve sahada fiyat sorulduğunda cevap veremiyorsun.

---

## AYLIK

| Gün | İş | Neden aylık | Zamanlayıcı |
|---|---|---|---|
| Ayın 1'i 04:30 | **Saha hedefleri — OSM taraması** | Eczane/klinik açılış-kapanış hızı bunu kaldırır; Overpass sunucuları paylaşımlı, sıklaştırmak başkasının kaynağını yakmak olur | `lcarlie-saha-tara` |
| Ayın 2'si 04:10 | **Katalog görselleri** — 124 ürün görseli Wix'ten çekilip WebP olarak indirilir | Görsel Wix'te nadiren değişir; var olan dosya yeniden indirilmez | `lcarlie-katalog-gorsel` |
| Haftalık (Cuma 05:26) | **Overture taraması** | Overture sürümü aylık çıkıyor ama sürüm tarihi sabit değil; haftalık bakmak yeni sürümü kaçırmamak için | `lcarlie-overture-tara` |

**Aylık, insan tarafı:**
1. Tarama sonrası hedef sayısındaki değişimi oku. Düşüş varsa sebebi
   kaynak mı, filtre mi — ikisi ayrı şey.
2. Elenen kayıtları gözden geçir (`SAHA` → "yalnız elenenler"). Yanlış
   elenmiş varsa `HEDEFTİR` ile geri al.
3. Kapanmış P0 kararları ve açık mevzuat bulguları: Wix'teki güneş kremi
   zorunlu ibare eksikliği hâlâ açık.

---

## ZAMANLAYICI OLMAYAN, AMA BEKLEYEN İŞLER

Bunlar **sahip kararı** gerektiriyor; kod tarafı hazır:

| İş | Ne bekliyor | Etkisi |
|---|---|---|
| **Bayi (toptan) fiyatı** | Sahip kararı — 36/36 ürün boş | Katalog eczaneye götürülebilir ama fiyat konuşulamaz. Uydurulmuş toptan fiyat sahada verilmiş yanlış sözdür |
| **Barkod çakışması** `8684869609301` | BUGUARD ve SOFTGUARD aynı barkodu taşıyor | Eczanede barkod okutulur; yanlış ürün satılabilir. Düzeltmek mevzuat/sahip kararı |
| **Güneş kremi zorunlu ibareleri** | Wix'te metin düzeltmesi | 3 üründe (BABYSOL, SUNACNEA, OPTYWAVE) zorunlu ibare eksik — denetim bunu belge düzeyinde bulguluyor |
| **7 üründe İngilizce INCI** | Etiketten doğrulama | Katalog "kaynağımızda yok" yazıyor; eczacının ilk sorusu içerik |
| **İlk saha günü** | Sahip / saha elemanı | 18.824 hedef hazır, **0 ziyaret**. Ölçüm halkası ilk ziyaretle kapanmaya başlar |

İlgili: `20-urunler.md`, `21-fiyat.md`, `10-iddia-kurallari.md`
