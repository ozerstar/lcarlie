---
konu: ölçüm gerçekleri ve veri tuzakları
anahtar: [ciro, satış, rakam, roas, marj, kâr, sipariş, ölçüm, veri, rapor,
  kaç sattık, ne kadar kazandık, reklam harcaması, dönüşüm, atıf, ga4, trafik,
  stok, envanter, kargo, panel]
gizlilik: serbest
---

# Ölçüm gerçekleri — bir sayı söylemeden önce oku

## Temel kural
**Ticari ölçüm 1 Ekim 2026'da başlar.** Öncesi için "ciro" tek bir sayı değildir.
Bilmediğim bir sayıyı tahmin etmem; **UNKNOWN derim.** Bu markada yanlış sayı,
eksik sayıdan pahalıya mal olmuştur.

## Nereden hangi veri geliyor
Ticari ayna `raw` → `core` → `mart` şeklinde katmanlıdır (CR-004).
Jarvis'in sorgulayabildiği alanlar sabit bir **izin listesidir** — liste dışı bir
soru cevapsız kalır, uydurma veriyle doldurulmaz.

| Alan | Durum |
|---|---|
| Satış / sipariş (Wix) | ✅ var |
| E-ticaret kalemleri | ✅ var |
| Reklam harcaması (Meta) | ✅ var — ayrı `AdsReader` kullanıcısı |
| CRM / konuşmalar | ✅ var |
| Operasyon | ✅ var |
| **GA4 / site trafiği** | ❌ DATA_UNAVAILABLE |
| **Gerçek stok / envanter** | ❌ DATA_UNAVAILABLE |
| **Günlük marj** | ❌ DATA_UNAVAILABLE |
| **BasitKargo** | ❌ bağlı DEĞİL |

## 🔴 Sayı tuzakları (hepsi gerçekten yaşandı)
1. **KDV.** Wix `toplam` alanı **KDV dahildir**. Bu yüzden marj bir dönem
   **%24,6 şişik** hesaplandı. KDV dahil ciroyla marj hesaplanmaz.
2. **Kalem indirimi.** Ciro bir dönem **%18,8 şişik** raporlandı; kaynak kalem
   bazlı indirimlerin düşülmemesiydi (CR-008).
3. **Maliyet gerçek değil.** 36 ürünün tamamında **₺400 elle girilmiş ortalama**
   maliyet var (kapsama %96,2). Marj bu yüzden **tahmindir**, ölçüm değildir.
4. **Ödemelerin %43'ünün otoritesi UNKNOWN.** Wix'in "tahsil edildi" demesi
   paranın alındığının kanıtı değildir; ödemelerin önemli kısmı çevrim dışı
   (kapıda ödeme / havale / WhatsApp satışı) yapılıyor.
5. **ROAS eksik ciroyla gösterilebiliyordu.** Artık bir **hazırlık kapısına**
   bağlı: kapı kapalıysa ROAS gösterilmez, günlük anlık görüntü alınır (CR-012).
6. **Atıf ölçüldü ve imkânsız çıktı.** Konuşmayı siparişe ad eşleşmesiyle
   bağlama denemesi **0 eşleşme** verdi (CR-011). "Bu konuşma satışa döndü mü"
   sorusunun cevabı yoktur; onun yerine **cevapsız mesaj** ölçülür.
7. **UNKNOWN ≠ NO_SALE.** Bir konuşma penceresinin kapanması satış olmadığının
   kanıtı değildir.
8. **Çakışan ikinci site.** BasitKargo ve bazı kayıtlar çakışan çift sitenin
   kendi hesabına aittir; karıştırılmaz.

## Ölçülmüş olan birkaç gerçek (varsayım değil)
- **Fiyat cevabı kalitesi:** 146 kişi VIREON fiyatını sordu, temiz "1.200 TL"
  cevabı alan **1 kişi** (17.09.2026).
- **Platform:** "Wix yavaş" varsayımı Lighthouse ile **çürüdü** — sitemiz 44,
  ikas ortalama 25, Shopify 30. Taşınma kararı yok. iframe'in bedeli 6,5 sn.
- **SPF:** SUNACNEA ölçülen 36,56 (etiket 30 ✅) · BABYSOL ölçülen 75,96
  (etiket 50+ ✅).
- **VIREON pazar konumu:** n=16 örneklemde net fiyat medyanı 376,98 TL, medyan
  8,36 TL/ml. VIREON 1.200 TL / 24,00 TL/ml → premium. (`21-fiyat`)
- ⚠️ **n=2 ile sonuç çıkarılmaz.** Bu kategoride ilk turda 2 ürünle varılan üç
  sonucun üçü de n=16'da çürüdü.

## Gelen kutusu ölçümü
- Sekmeler tek tek gezilmez; **kırmızı bildirim rozetine** bakılır.
- **"Okunmamış" filtresi cevapsız mesajı gizliyor** — filtresiz "Tüm mesajlar"
  listesine bakılır.
- Instagram'da bazı reklam-yanıtları hiç yanıt almıyor (Meta tarafı sorunu,
  aktif izleniyor). Gelen DM trafiğinin **~%92'si VIREON**'a geliyor.

## Açık operasyonel sorunlar
- `rclone` yedek kotası — AÇIK SORUN (CR-005).
- Sunucuda konteynerler SIGKILL ile ölüyor; kapanış işleyicileri çalışmıyor
  (docker/runc uyumsuzluğu).
