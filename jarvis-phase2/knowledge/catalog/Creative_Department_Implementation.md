# CREATIVE DEPARTMENT — UYGULAMA BELGESİ

Sürüm 1 · 26.09.2026 · dal `katalog-zeka-v1`

Bu belge, L'CARLIÉ katalog Creative Department'ının **çalışan**
uygulamasını anlatır. "Tanımlı" ile "çalışıyor" burada ayrılır:
her capability'nin dosyası, testi ve gerçek veri üzerindeki sonucu
yazılıdır.

---

## 1 · Üretim akışı

```
ürün fotoğrafı
   │
   ├─▶ 1. PRODUCT ASSET CLASSIFIER        katalog_varlik.py
   │      TYPE A/B/C/D + izin matrisi     ← ZORUNLU İLK KAPI
   │      TYPE D ise üretim DURUR
   │
   ├─▶ 2. FOTOĞRAF ANALİZİ                katalog_foto_analiz.py
   │      palet · ışık yönü · saliency vekili · ürün sınır kutusu
   │      negatif alan · metin güvenli bölge · zemin modeli
   │      kadraj fırsatları (her biri mm cinsinden azami yerleşimle)
   │
   ├─▶ 3. ART DIRECTION                   katalog_konsept.py
   │      sınıfa göre iskelet havuzu; 3 CİDDİ konsept
   │      TYPE A → bütün-görüntü iskeletleri (kırpma yasak)
   │      TYPE B → sıkı kadraj iskeletleri
   │      KAPAK  → kendi havuzu (künye taşımaz)
   │
   ├─▶ 4. KANIT ÖLÇÜMÜ                    katalog_sayfa_olcum.py
   │      her konsept render edilir ve ölçülür
   │      ürün yük. oranı · boşluk · öğe · ölçek kontrastı · imza
   │
   ├─▶ 5. ECD SEÇİMİ                      katalog_pilot.ecd_secimi
   │      ölü boşluk elemesi → tekrar kuralı → AD tercihi → kanıt
   │      SKOR ÜRETİLMEZ; gerekçe metni yazılır
   │
   ├─▶ 6. RENDER                          katalog_render.py
   │      görüntü katmanı PIL (ürünün NATIVE DPI'ında)
   │      metin katmanı VEKTÖR (reportlab)
   │      yukarı örnekleme → ValueError
   │
   ├─▶ 7. KAPILAR
   │      TYPOGRAPHY QA        katalog_tipografi_qa.py   (durdurur)
   │      METİN/GÖRÜNTÜ KONTRAST  katalog_render.py      (durdurur)
   │      INDEPENDENT CRITIC   katalog_pilot.elestirmen  (durdurur)
   │      ÜRÜN BÜTÜNLÜĞÜ       katalog_butunluk.py       (aşılamaz)
   │
   └─▶ 8. REVİZYON (en fazla 3 tur) → TESLİM
```

---

## 2 · Capability durumu — ölçülmüş

| # | Capability | Dosya | Durum | Kanıt |
|---|---|---|---|---|
| C07A | Product Asset Classifier | `katalog_varlik.py` | **ÇALIŞIYOR** | 5 pilotu sınıfladı; editoryal→A, packshot→B |
| — | Fotoğraf analizi | `katalog_foto_analiz.py` | **ÇALIŞIYOR** | 5 üründe sınır kutusu görsel doğrulandı |
| C07 | Art Director | `katalog_konsept.py` | **ÇALIŞIYOR** | sınıfa göre 8 iskelet, sayfa başına 3 konsept |
| C01 | Executive Creative Director | `katalog_pilot.ecd_secimi` | **ÇALIŞIYOR** | kanıtla seçim, gerekçe yazılı |
| C08 | Editorial Designer | `katalog_tasarim_sistemi.py` | **ÇALIŞIYOR** | 210×210 grid, 8 sütun, taban 4,2 mm |
| C09A | Typography Art Direction | `katalog_tasarim_sistemi.TIP` | **ÇALIŞIYOR** | 12 rol; not alanı rolü dahil |
| C09B | Typography QA | `katalog_tipografi_qa.py` | **ÇALIŞIYOR** | 2 sayfayı reddetti, revizyona gönderdi |
| — | Metin/görüntü kontrast | `katalog_render.py` | **ÇALIŞIYOR** | kapağı 3 turda reddetti → kapak iskeleti yazıldı |
| C10 | Photography & Retouch | `katalog_render.py` | **KISMİ** | zemin genişletme var; ışık/gölge ölçümü yok |
| C12 | Product Integrity Guardian | `katalog_butunluk.py` | **ÇALIŞIYOR** | her sayfa için `koken.json` |
| C13 | Independent Critic | `katalog_pilot.elestirmen` | **ÇALIŞIYOR** | brief'i görmez; yalnız render ölçümü |
| C05/C06 | Copy / Regulatory | içerik katmanı | **KISMİ** | metinler doğrulanmış kaynaktan; otomatik denetim bağlı değil |
| C15 | Prepress | `katalog_tipografi_qa` + ölçüm | **KISMİ** | taşma/güvenli alan/font var; ICC ve TAC yok |
| C11 | Image Generation Supervisor | — | **KULLANILMADI** | PC-2 erişilemez (port 8188 kapalı, ölçüldü) |

---

## 3 · İskelet havuzu

| iskelet | sınıf | tanım |
|---|---|---|
| `fotografik_hakimiyet` | B | ürün sağdan taşar, solda doygun dikey blok |
| `yatay_ufuk` | B | ürün sağ alttan taşar, üst yarı sessiz |
| `kontrollu_asimetri` | B | üst blok + ürün sol alttan taşar |
| `tam_kare` | A | bütün görüntü yatay bant, üst/alt bantlar tipografiye |
| `kare_blok` | A | bütün görüntü sağ alt kare, solda renk alanı |
| `ust_blok` | A | üst blok + bütün görüntü sol alttan taşar |
| `kapak_tam_bleed` | KAPAK | tam sayfa fotoğraf + alt marka bandı |
| `kapak_bolunmus` | KAPAK | üst marka alanı + alt fotoğraf |

**Kural:** aynı iskelet katalogda iki kez kullanılamaz.

---

## 4 · Bu üretimde ölçülen ve düzeltilen kusurlar

Her biri gerçek render üzerinde bulundu; hiçbiri varsayımla
düzeltilmedi.

| # | Kusur | Kök neden | Düzeltme |
|---|---|---|---|
| 1 | Ürün sınır kutusu 4/5 üründe yanlış | Vinyetli fonda medyan renk çıkarmak yetmiyor | Zemin ikinci derece yüzey olarak modellendi; kalıntı + kenar enerjisi birlikte |
| 2 | HYDRAVIE'de duvar gölgesi maskeye karıştı | Sert gölgenin kenarı ürün kenarı kadar keskin | İnsan doğrulamalı geçersiz kılma, kayda geçirildi |
| 3 | KINESIS'te sarı kutu maskeden düştü | Tepe koşusu iki parçalı üründe fazla sıkı | Renk kalıntısı + kenar kapısıyla geri alma |
| 4 | Renk alanları soluk — "pastel kutu" hissi | Vurgu rengi aşırı soluklaştırılıyordu | Alanlar ürünün kendi doygun renginden |
| 5 | Fotoğraf "yapıştırılmış dikdörtgen" | Renk alanının üzerine dikdörtgen yerleşim | Fotoğraf sayfa kenarlarından taşar; yalnız iç kenar tüylenir |
| 6 | Blok–fotoğraf arasında çentik | Blok tabanı ile fotoğraf üstü hizasız | Tam hizalama |
| 7 | Sağ alt %40 ölü boşluk | Künye kısa, kolon boş | INCI + not alanı ile dolduruldu |
| 8 | Not alanı kaybolmuştu | Yeniden yazımda düştü | `_not_bloku` ortak blok olarak eklendi |
| 9 | Kapakta başlık fotoğraf üzerinde okunmuyor | Kontrast hiç ölçülmüyordu | **Metin/görüntü kontrast kapısı yazıldı** |
| 10 | Kare fotoğraf tüm sayfayı kaplıyordu | `tam_kare` yükseklik sınırı yoktu | Yükseklik %54'e sınırlandı, bantlar korundu |
| 11 | İkincil metin krem zeminde 3,0 kontrast | Gri 0,44 çok açık | 0,30'a koyulaştırıldı |
| 12 | Koyu fotoğraf zemininde koyu mürekkep | Mürekkep varsayılıyordu | `zemin_murekkebi()` ölçülen zeminden türetir |
| 13 | INCI not alanı çizgileriyle çakıştı | Sabit ofset | Akış gerçek satır sayısından hesaplanıyor |
| 14 | `·` ayracı .notdef kutusu basıyordu | **Metropolis'te U+00B7 glifi yok** | Metropolis metinlerinde otomatik `–` ikamesi |
| 15 | Zorunlu güneş kremi uyarısı basılmıyordu | Alan tanımlıydı ama render edilmiyordu | Mevzuat gereği not bloğunun üstüne basılıyor |
| 16 | Vektör çizimler hiç sayılmıyordu | `get_text`/`get_image_info` vektör görmüyor | `get_drawings()` eklendi |

---

## 5 · Çözünürlük gerçeği

**Ölçüldü ve doğrulandı (görsel eşleştirme):** 5 pilot ürünün
kaynakları **1254×1254 px** ve bundan büyüğü sistemde **yok**.

| ürün | sıkı kadraj px | 200 DPI'da |
|---|---|---|
| HYDRAVIE | 413 × 1053 | 52 × 134 mm |
| FEMISIA | 409 × 1029 | 52 × 131 mm |
| KINESIS | 753 × 787 | 96 × 100 mm |
| BABYSOL | 723 × 812 | 92 × 103 mm |

**Eski katalog bu ürünleri ~97 mm genişlikte basmıştı** — bu
yaklaşık 2,3× büyütme demektir. Bu sistem büyütmeyi reddeder ve
bunun yerine native pikselleri 200 DPI'da yayar.

---

## 6 · Bağımlılık

**Bu fazda eklenen paket: 0.** Kullanılanların tamamı zaten kuruluydu:
`pillow`, `numpy`, `scipy`, `reportlab`, `fonttools`, `pymupdf`.

ComfyUI kullanılmadı — PC-2 erişilemez durumdaydı.

---

## 7 · Rollback

- Dal: `katalog-zeka-v1` · etiket `faz-1b-tamam` (pilot öncesi durum)
- Worktree: `/opt/lcarlie/source/worktrees/katalog-zeka`
- Çalışan hiçbir servise, timer'a, n8n akışına, satış sistemine veya
  mevcut kataloglara dokunulmadı
- `lcarlie-katalog-uret.timer` **değiştirilmedi**; yeni modüller
  üretim hattına bağlanmadı

---

## 8 · Açık işler

| # | İş | Neden bu fazda yapılmadı |
|---|---|---|
| 1 | Saliency modeli | PC-2 erişilemez; şimdilik CV vekili kullanılıyor |
| 2 | ComfyUI sahne üretimi | PC-2 erişilemez |
| 3 | ICC / CMYK / TAC | matbaa ve kâğıt seçilmedi |
| 4 | Anlamsal metin tekrarı | gömme hattı katalog metnine bağlanmadı |
| 5 | Mevzuat denetçisinin otomatik bağlanması | metinler elle doğrulanmış kaynaktan alındı |
| 6 | Işık yönü / temas gölgesi ölçümü | TYPE A kullanıldığı için kompozit gerekmedi |
