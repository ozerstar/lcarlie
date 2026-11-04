# Jarvis Görevi: L'CARLİÉ Rakip Radarı

Bu dosya, Jarvis'in rakip keşif ajanına verilecek görev tanımıdır. Ajan her sabah iki kez çalışır:
- **tarama (05:00):** Yeni markaları bulur, izlenen markaların güncel verisini toplar.
- **teyit (06:00):** Yalnızca `scans/teyit.json` içindeki linkleri yeniden açar ve aynı veriyi tekrar okur.

Ajan çıktısını JSON olarak yazar; L'CARLİÉ Radar bu JSON'u doğrular. **Kurallara uymayan her satır reddedilir.**

## Değişmez kurallar
1. **Tahmin etme, uydurma.** Bir bilgiyi sayfada göremiyorsan `not_found` yaz.
2. Her gözlemde `source_url` (bilgiyi gördüğün sayfanın tam linki) ve `fetched_at` (o anın saati, ISO) olacak.
3. Sayısal her bilgide (fiyat, yorum sayısı, reklam sayısı, takipçi) `excerpt` alanına sayfadaki metni **aynen kopyala**. Sayı alıntıda geçmezse kayıt reddedilir.
4. Yalnızca herkese açık sayfalar. Giriş yapma, captcha geçme, ücretli içerik açma yok.
5. Renkli kozmetik (makyaj) markalarını hiç ekleme. İlaç / reçeteli ürünleri ekleme.
6. Bir sayfa açılmıyorsa `source_status` içine `ok:false` ve hata yaz. Sessizce atlama.

## Ne aranacak (keşif)
L'CARLİÉ'nin fiyat bandı: çoğu ürün 900–2.400 TL (perakende). Kategoriler: yuz, vucut, bebek, gunes, sac, intim, dudak, agiz_dis, roll_on, sprey.

Aşağıdaki gruplardan **her gün her gruptan birkaç arama** yap:
1. **Aynı fiyat veya bizden pahalı:** Trendyol'da "dermokozmetik krem", "bitkisel bakım kremi", "intim bakım kremi", "gece kremi" aramaları, fiyatı yüksekten düşüğe.
2. **Yeni giren markalar:** "yeni dermokozmetik markası", Trendyol'da yeni açılan mağazalar, son 12 ayda kurulan markalar. Giriş tarihini biliyorsan `first_seen_hint` yaz (ör. ilk ürün yorumunun tarihi).
3. **Doğal içerikli kremler:** "doğal içerikli krem", "organik krem", "vegan cilt bakım".
4. **Tedavi eder gibi görünen ama ilaç olmayan kremler:** "bitkisel merhem", "aktar kremi", "balsam", "onarıcı krem", "kaşıntı kremi bitkisel", "nasır kremi".
5. **Eczane ve Rossmann'da satılanlar:** rossmann.com.tr cilt bakım kategorileri, online eczane sitelerinin dermokozmetik bölümleri.
6. **Ek:** Kore/Avrupa ithal dermokozmetikler; Meta Reklam Kütüphanesi'nde (facebook.com/ads/library, ülke: Türkiye) çok sayıda aktif reklamı olan cilt bakım markaları.

**İzlenen markalar** (`scans/izlenen.json`, Özer'in onayladıkları): her biri için Trendyol mağazası, kendi sitesi, Instagram ve Reklam Kütüphanesi'ni kontrol et; ürün listesini ve fiyatları eksiksiz yaz (yeni ürün ve fiyat değişikliği buradan yakalanır).

## Çıktı formatı
```json
{
  "source": "jarvis-tarama",
  "source_status": [
    {"source": "trendyol", "ok": true},
    {"source": "rossmann.com.tr", "ok": false, "error": "403"}
  ],
  "brands": [
    {
      "name": "Marka Adı",
      "website": "https://...",
      "instagram": "https://instagram.com/...",
      "trendyol_url": "https://www.trendyol.com/magaza/...",
      "origin": "TR",
      "first_seen_hint": "2026-05-10",
      "texts": ["Marka/ürün açıklamasından kısa alıntılar: 'bitkisel içerikli onarıcı balsam, eczanelerde'"],
      "observations": [
        {"kind": "price", "product": "Onarıcı Balsam 50 ml", "category": "vucut", "value": 1450,
         "source_url": "https://www.trendyol.com/...-p-123", "fetched_at": "2026-10-30T05:12:00+03:00",
         "excerpt": "Onarıcı Balsam 50 ml 1.450 TL"},
        {"kind": "product", "product": "Yeni Gece Serumu", "source_url": "https://...", "fetched_at": "..."},
        {"kind": "channel", "value": "eczane", "source_url": "https://...", "fetched_at": "..."},
        {"kind": "review_count", "value": 1234, "source_url": "https://...", "fetched_at": "...", "excerpt": "1.234 Değerlendirme"},
        {"kind": "ad_count", "value": 18, "source_url": "https://www.facebook.com/ads/library/?...", "fetched_at": "...", "excerpt": "~18 sonuç"},
        {"kind": "follower_count", "value": 45000, "source_url": "https://instagram.com/...", "fetched_at": "...", "excerpt": "45.000 takipçi"},
        {"kind": "claim", "value": "Reklam metni aynen", "source_url": "https://...", "fetched_at": "..."},
        {"kind": "not_found", "product": "Fiyat", "source_url": "https://...", "fetched_at": "..."}
      ]
    }
  ]
}
```
`channel` değerleri: `eczane`, `rossmann`, `gratis`, `watsons`, `trendyol`, `hepsiburada`, `kendi_sitesi`.

## Teyit modu
`scans/teyit.json` içindeki her satır için yalnızca `source_url` sayfasını yeniden aç, aynı ürünün güncel fiyatını/varlığını yukarıdaki formatla yaz. Başka marka ekleme.

## Rakip reklam metinleri
Rakibin TİTCK'ye aykırı görünen iddialarını `claim` olarak kaydedebilirsin; bunlar sadece bilgi içindir, L'CARLİÉ içeriğine **asla** taşınmaz.
