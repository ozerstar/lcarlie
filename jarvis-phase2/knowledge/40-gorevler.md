---
konu: Katalog, saha ve sosyal medya için günlük/haftalık/aylık görevler
anahtar: [gorev, görev, gunluk, günlük, haftalik, haftalık, aylik, aylık, katalog, saha, instagram, zamanlayici, zamanlayıcı, takvim, rutin]
gizlilik: ic-bilgi
kaynak: /etc/systemd/system/lcarlie-*.timer (systemctl list-timers)
uretim: elle yazıldı 25.09.2026
---

# Görev takvimi — katalog, saha, sosyal medya

Her satırın karşılığı çalışan bir systemd zamanlayıcısıdır: yapılacak
listesi değil, **yapılanın kaydı**.

🔴 **ÜRETİLEN HİÇBİR ŞEY KENDİLİĞİNDEN YAYINLANMAZ.** Dış eylem kapalı
(`EXTERNAL_ACTIONS=false`). Jarvis hazırlar, sahip panelden onaylar.

## GÜNLÜK

**05:20 · `lcarlie-katalog-uret`** — 36 ürünün metni yayındaki Wix
açıklamasından yeniden çıkarılır, her cümle mevzuat denetçisinden geçer.
*Neden günlük:* Wix metni elle düzeltilebiliyor (güneş kremlerindeki
zorunlu ibare eksikliği gibi). Haftalık olsaydı eczaneye eski metin
götürülürdü.

Ayrıca mevcut: 06:20 sayfa ölçümü · 07:45 güncel olaylar · 08:17 yönetici
brifingi · 08:30 tasarım nöbeti.

**İnsan tarafı (karar gerektirir, zamanlayıcı yok):**
1. `KATALOG` sekmesindeki uyarı satırı: eksik INCI, eksik bayi fiyatı,
   barkod çakışması orada yazar.
2. `INSTAGRAM PLANI`nda karar bekleyen paketi onayla ya da reddet. Karar
   verilmeyen paket yeni paket üretilmesini **engeller** — yığılmış liste
   okunmaz.
3. `SAHA`da o gün gidilecek rotayı çıkar.

## HAFTALIK

**Pazartesi 06:10 · `lcarlie-ig-gonderi`** — gönderi paketleri ölçülmüş
veriden üretilir: 124 gönderinin etkileşimi, 63 reklam kreatifinin
maliyeti, gerçek satış sinyali. *Neden haftalık:* paket üretmek bedava,
**karar vermek** değil; günlük koşsaydı sahip 7 günde 49 paketle
karşılaşır ve hiçbirine bakmazdı.

Ayrıca mevcut: Cumartesi 10:11 kreatif hattı.

**İnsan tarafı:**
1. Onaylanan gönderiyi çek/tasarla, yayınla, panelde `YAYINLANDI`
   işaretle. İşaretlenmeyen paket "onaylandı ama yapılmadı" olarak durur.
2. `mart.katalog_ilgi`: hangi ürün ilgi görüyor, hangisi görmüyor.
3. Bayi fiyatı girilmemiş ürün kaldıysa karar ver — katalog onu "—" ile
   gösteriyor, sahada fiyat sorulduğunda cevap veremiyorsun.

## AYLIK

**Ayın 1'i 04:30 · `lcarlie-saha-tara`** — OSM taraması. *Neden aylık:*
eczane/klinik açılış hızı bunu kaldırır; Overpass sunucuları paylaşımlı.

**Ayın 2'si 04:10 · `lcarlie-katalog-gorsel`** — 124 ürün görseli WebP
olarak indirilir. Var olan dosya yeniden indirilmez.

**Cuma 05:26 · `lcarlie-overture-tara`** — sürüm tarihi sabit olmadığı
için haftalık bakılır, aylık yenilenir.

**İnsan tarafı:** hedef sayısındaki değişimi oku (düşüş varsa sebebi
kaynak mı filtre mi — ikisi ayrı şey) · `SAHA` → "yalnız elenenler"de
yanlış elenmiş varsa `HEDEFTİR` ile geri al.

## ZAMANLAYICISI OLMAYAN, SAHİP KARARI BEKLEYEN

| İş | Etkisi |
|---|---|
| **Bayi (toptan) fiyatı** — 36/36 boş | Katalog götürülebilir ama fiyat konuşulamaz. Uydurulmuş toptan fiyat, sahada verilmiş yanlış sözdür |
| **Barkod çakışması** `8684869609301` | BUGUARD ve SOFTGUARD aynı barkodda; eczanede yanlış ürün satılabilir |
| **Güneş kremi zorunlu ibareleri** | BABYSOL, SUNACNEA, OPTYWAVE'de eksik — Wix'te düzeltilecek |
| **7 üründe İngilizce INCI yok** | Katalog "kaynağımızda yok" yazıyor; eczacının ilk sorusu içerik |
| **İlk saha günü** | 18.824 hedef hazır, **0 ziyaret**. Ölçüm halkası ilk ziyaretle kapanır |

İlgili: `20-urunler.md`, `21-fiyat.md`, `10-iddia-kurallari.md`
