---
konu: Aylik gorevler ve zamanlayicisi olmayan, sahip karari bekleyen isler
anahtar: [gorev, görev, aylik, aylık, saha, tarama, overture, osm, katalog, gorsel, görsel, bayi, toptan, barkod, inci, karar, bekleyen]
gizlilik: ic-bilgi
kaynak: /etc/systemd/system/lcarlie-*.timer (systemctl list-timers)
uretim: 40-gorevler.md dosyasindan bolundu 25.09.2026 -- tek dosya 4200
  karakterlik getirme butcesini asiyordu ve SESSIZCE hic getirilmiyordu
---

# Aylik gorevler ve bekleyen kararlar

Gunluk ve haftalik isler icin: `40-gorevler.md`

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
