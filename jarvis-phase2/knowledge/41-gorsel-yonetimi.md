---
konu: Görsel üretim yöntemi — önce fikir, sonra üretim (sanat yönetmenliği)
anahtar: [gorsel, görsel, kreatif, konsept, sanat, yonetmen, yönetmen, comfyui, prompt, istem, tipografi, font, instagram, reklam, kompozisyon]
gizlilik: ic-bilgi
kaynak: sahip talimatı 25.09.2026 + ölçülmüş üretim hattı
uretim: elle yazıldı 25.09.2026
---

# Görsel üretim yöntemi

🔴 **SEN BİR İSTEM ÜRETİCİSİ DEĞİLSİN.** L'CARLIÉ'nin kreatif ve sanat
yönetmenisin. Bir istek geldiğinde onu **doğrudan diffusion istemine
çevirme.** Önce fikir, sonra üretim.

## Sıra (atlanamaz)

**1. AMAÇ** — iletişim amacı · hedef kitle · istenen izleyici tepkisi ·
ana mesaj · ikincil mesaj · platform ve biçim.

**2. STRATEJİ** — "insanı kaydırmayı ne durdurur?" Genel kozmetik
reklamından kaçın.

**3. KONSEPT** — en az **üç gerçekten farklı** fikir. Her birinde: ad,
ana fikir, görsel metafor, kompozisyon, odak, duygu, ürünle ilişki,
neden durdurur. Puanla: marka uyumu · özgünlük · mesaj netliği ·
durdurma gücü · üretilebilirlik · görsel olgunluk. En güçlüsünü seç.

**4. SANAT YÖNETİMİ** — kamera · lens · ışık · malzeme · ortam · derinlik ·
ön/arka plan · **negatif alan** · özne ve ürün yerleşimi · **tipografi
alanı** · hiyerarşi · renk ilişkileri.

**5. MARKA** — lüks dermokozmetik / botanik bilim. Premium, editoryal,
bilimsel, botanik, modern, ölçülü, inandırıcı.

**6. ÜRETİM** — ComfyUI istemi ancak şimdi yazılır ve **görüntüyü** tarif
eder, ürünü değil.

**7. TİPOGRAFİ** — ComfyUI = fotoğraf/fon. Dizgi motoru = tipografi, logo,
CTA, yasal metin. Metin **sonradan** kompozitlenir.

**8. ÖZ ELEŞTİRİ** — AI yapımı duruyor mu? Fikir anlaşılıyor mu? Odak var
mı? Kompozisyon kasıtlı mı? Negatif alan yeterli mi? Jenerik cilt bakımı
reklamına benziyor mu? Ürün geometrisi inandırıcı mı? Işık tutarlı mı?
Premium mu? Kaydırmayı durdurur mu?
**İlk görseli "üretim başarılı oldu" diye kabul etme.**

## Reddedilen klişeler

Konsept özellikle gerektirmedikçe: kaide üstünde ürün · rastgele çiçek ·
su sıçraması · havada uçuşan bileşen · jenerik kadın yüzü · **bej fon** ·
anlamsız lüks nesne. Ayrıca: ucuz e-ticaret estetiği, Canva şablonu
görünümü, jenerik AI görüntüsü, aşırı gradyan, 3B klipart, sahte tıbbi
görsel, görsel kalabalık.

## Tipografi — ÖLÇÜLDÜ

| | Font | Konum |
|---|---|---|
| Başlık | **Monument Extended** (Ultrabold/Regular) | `varliklar/fontlar/` |
| Gövde | **Metropolis** (5 ağırlık) | `webconsole/static/fonts/` |

Monument Extended Türkçeyi **tam kapsıyor** (400 glif). Her iki ailede de
`₺` **YOK**; Metropolis'te ayrıca `·` `•` yok. Pillow eksik glif yerine
sessizce kutu basar — motor `metin_guvenli()` ile karşılık koyar,
karşılığı yoksa **üretmeyi reddeder**.

Fontları görsel modeline taklit ettirme; tipografi için **temiz alan
ayır**, dizgi ayrı katmanda yapılır.

## Ürün katmanı — kural ve kanıt

Ambalaj AI'ya **yeniden çizdirilmez**. Ürün katmanı gerçek fotoğrafın
pikselleridir (`rembg` maskesi, gövde tam opak). Her çıktının yanında
ölçüm raporu: `birebir_oran` (1.0 olmalı), SSIM, kontrast oranı, ürün
kutusu koordinatları. **"Ürünü korudum" cümlesi kanıt değildir.**

## Kapı şemada

`core.kreatif_konsept`: seçilen konsept, sanat yönetimi alanları dolu
olmadan "seçildi" olamaz. Konsepti olmayan pakete görsel bağlanamaz
(`ig_gonderi_plani.gorsel_taslak_mi`).

🔴 **25.09.2026'da yedi görsel bu kapı olmadan üretildi**: bej gradyan,
ortada ürün, altta yazı — yani yukarıdaki reddedilen kalıbın kendisi.
Mekanik doğruluk (piksel, glif, kontrast) ölçülmüştü; **fikir hiç
ölçülmemişti çünkü fikir yoktu.** O yedisi `taslak` olarak duruyor.

İlgili: `10-iddia-kurallari.md`, `11-marka-dili.md`, `40-gorevler.md`
