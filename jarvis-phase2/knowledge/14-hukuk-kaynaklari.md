---
konu: Hukuk birimi kaynakları — Mizan-27B Türk hukuku karar modeli
anahtar: [hukuk, hukuki, mevzuat, kanun, yönetmelik, yargı, dava, sözleşme, kvkk, tazminat, ihtar, mizan, avukat, hukukçu, uyum, yasal, yasa]
gizlilik: ic-bilgi
---

# Hukuk birimi kaynakları

🔒 İÇ BİLGİ. Sahip kararı 28.11.2026: Mizan-27B, hukuk biriminin (Yayın Hukuk ve Mevzuat Denetçisi, Tasarım Mevzuat Denetçisi, İddia Envanteri Uzmanı) kaynaklarından biridir.

## Mizan-27B nedir
- Türk hukukuna özel açık ağırlıklı model (Alican Kiraz, Qwen3.6-27B tabanlı).
- Metin yazmaz. Olay metnini ve soruları alır, her soru için olasılıklı bir karar verir.
- Hazır sorular: hukuk_alani, temel_mevzuat, yargi_yolu, talep_sonucu, sure_sorunu, karmasiklik. Özel evet/hayır ve seçmeli sorular JSON ile eklenebilir.

## Nasıl kullanılır (indirme/kurulum yok)
- Tarayıcıda: https://huggingface.co/spaces/AlicanKiraz0/Mizan-27B-Turkish-Legal-Decision-Model
- Olay metni yazılır, sorular seçilir, "Karar ver"e basılır. Claude Chrome üzerinden çalıştırabilir.
- İlk istek 30–60 sn sürebilir. Girişsiz günlük kota yaklaşık 2 dk; Hugging Face hesabıyla 5 dk.
- Olay metnine müşteri adı, T.C. no, telefon gibi kişisel veri yazılmaz. Olay anonim anlatılır (KVKK).

## Ne için, ne için değil
- ✅ İlk tarama: konu hangi hukuk alanı, hangi kanun, hangi mahkeme, süre sorunu var mı, iş ne kadar karmaşık. Avukata gitmeden önce soruyu netleştirmek.
- ❌ Hukuki tavsiye veya nihai karar değildir. Geliştiricinin bildirdiği %94,9 uyumu bağımsız hukukçular doğrulamamıştır; istisna ve süre sorularında yaklaşık %78'e düşer.
- Her sonuç resmî kaynakla teyit edilir (mevzuat.gov.tr, Resmî Gazete, Yargıtay/Danıştay karar arama). Kritik işte (dava, ihtar, sözleşme imzası, mevzuat cezası riski) avukat görüşü şarttır.
- Reklam ve ürün iddiası denetiminde öncelik `10-iddia-kurallari` ve `13-kapanmis-kararlar`daki kendi kurallarımızdır; Mizan bunların yerine geçmez.

## Lisans uyarısı
Model CC BY-NC 4.0 (ticari olmayan kullanım) lisanslıdır. Şirket içi ön tarama için kullanılır. Müşteriye sunulan bir hizmete veya ücretli bir ürüne gömülmez. Çıktısı dışarıya "hukuki görüş" diye verilmez.
