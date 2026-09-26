# L'CARLIÉ CATALOG DESIGN CONSTITUTION — V1

> **DURUM: YÜRÜRLÜKTE.** Bu sürüm sisteme bağlıdır. Aşağıdaki
> maddelerin ölçülebilir kısımları `jarvis/katalog_*.py` içinde kapı
> olarak çalışır ve üretimi durdurabilir.
>
> Sürüm 1 · 26.09.2026 · 5 pilot sayfa üzerinde doğrulandı.

---

## Yazım ilkesi

Bu anayasa **koşullu tasarım ilkeleri** yazar. Şu biçimdeki maddeler
bilerek yoktur: *"ürün %50 büyük olsun"*, *"bol boşluk premiumdur"*,
*"ürün crop edilmez"*. Böyle bir kural yeni bir şablon üretir ve
çözmeye çalıştığı sorunu yaratır.

Her madde: **koşul → değerlendirme → ölçülebilir kısım → kimin kararı.**

Eşiklerin tamamı bu projede **ölçülmüştür**. Tahminle konmuş eşik
yoktur; ölçülemeyen yerde eşik de yoktur, yargı vardır.

---

## BÖLÜM I — VARLIK VE ÜRÜN

### 1 · Varlık sınıflandırması zorunlu ilk kapıdır

Hiçbir ürün görseli sınıflandırılmadan işleme giremez.

| sınıf | tanım | varsayılan |
|---|---|---|
| **A** | Editoryal: kompozisyon, ışık, arka plan tasarlanmış | **DOKUNMA** |
| **B** | Stüdyo: profesyonel çekim, sahne nötr | Kontrollü genişletme |
| **C** | Packshot: izole ürün | Kompozit uygulanabilir |
| **D** | Yetersiz kaynak | **ÜRETİM DURUR** |

**Uygulama:** `jarvis/katalog_varlik.py` · yasak işlem `VarlikIhlali`
fırlatır.

**Ölçüldü:** 5 pilot ürünün editoryal varyantları TYPE A, düz
packshot'ları TYPE B olarak sınıflandı. Sınıf, hangi iskeletlerin
kullanılabileceğini belirledi.

### 2 · TYPE A'da ürüne kırpma yasaktır

Editoryal fotoğrafta yasak: arka plan kaldırma, otomatik ürüne kırpma,
ürün veya etiket yeniden üretimi, arka plan değiştirme, geometri
değişikliği.

İzinli: bozucu olmayan sayfa yerleşimi, **gerekçeli bütün-görüntü
kırpma**, renk yönetimli yerleşim, fotoğraftan türetilen düzen.

**Neden:** kesim adımı basılabilir ölçünün ~%75'ini götürüyor.
Ölçüldü: kaynak medyanı 106 mm, kesim medyanı 25 mm (300 DPI).

### 3 · Büyük yerleştirmek ≠ büyütmek

**Bu ayrım bu sistemin temelidir.**

Büyütme piksel **uydurur**. Düşük DPI'da yerleştirme gerçek pikselleri
daha geniş alana **yayar** — yeni bilgi uydurmaz.

- Ürün görüntüsü için taban: **200 DPI**
- Üretilen/genişletilmiş zemin için taban: **150 DPI**
- Hedef: 300 DPI

**Yukarı örnekleme kesinlikle yasaktır.** Render motoru hedef ölçü
kaynağı aşarsa `ValueError` fırlatır ve sayfa üretilmez.

**Ölçüldü:** 5 pilot ürünün kaynakları 1254×1254 px ve bundan büyüğü
sistemde yok (görsel eşleştirmeyle doğrulandı). Bu tavanla ürünler
131–159 mm yüksekliğe kadar **büyütmeden** yerleştirilebiliyor.

### 4 · Ürün bütünlüğü — aşılamaz

Gerçek ürün, ambalaj, etiket ve logo pikselleri **hiçbir koşulda**
üretken modelden geçemez. Köken kaydı yoksa sonuç BİLİNMİYOR'dur ve
**geçmez**.

**Uygulama:** `jarvis/katalog_butunluk.py` · her pilot sayfa için
`koken.json` yazılır.

---

## BÖLÜM II — KOMPOZİSYON

### 5 · Ürün baskınlığı boyut değildir

Sabit yüzde kuralı **yasaktır**.

Baskınlığı belirleyen: fiziksel ölçü, görünür alan, **kontrast (en
güçlü tek faktör)**, konum, izolasyon, keskinlik, çevre yoğunluğu,
saliency, aydınlatma, önplan baskınlığı, kadraj, kenar etkileşimi,
arka plan rekabeti.

Önce sayfanın rolü belirlenir (HERO / ANLATI / KATALOG / DETAY /
SESSİZ), sonra baskınlık profilinin o role uyup uymadığına bakılır.

**Ret koşulu:** sayfa rolü HERO veya KATALOG iken ürünün saliency payı
eşiğin altındaysa — ürün büyük olsa bile.

### 6 · Kırpma felsefesi

Kırpma ürün kimliğini yok ediyorsa başarısızdır. Kasıtlı aşırı kadraj
görsel baskınlık, ölçek kontrastı veya editoryal gerilim üretiyorsa
başarılıdır.

**Düşük kırpma korunumu otomatik olarak kötü değildir.** Ölçüm ile
yargı ayrı tutulur: `kirpma_korunumu()` yargı içermez.

### 7 · Aktif ve ölü boşluk

Boşluk kendiliğinden premium değildir.

**Ölü boşluğun ölçülebilir imzası:** boşluk oranı > 0,62 **ve** öğe
sayısı < 8. Bu kombinasyon konsept elemesinde kullanılır.

**Eleştirmen eşiği:** boşluk > 0,66 ve öğe < 9 → YÜKSEK ağırlıklı
itiraz, sayfa revize edilir.

"Lüks kısıtlama" gerekçesiyle savunulamaz.

### 8 · Fotoğraf sayfaya yapıştırılmaz

**Ölçüldü ve düzeltildi:** fotoğrafı renk alanının üzerine dikdörtgen
olarak koymak "yapıştırılmış" kusuru üretiyordu.

**Kural:** fotoğraf sayfa kenarlarından taşar; yalnız iç kenarları
tüylenir. Görünen tek kenar bilinçli kompozisyon çizgisidir.
Sayfadan taşan kenar **tüylenmez** — baskıda soluk şerit bırakır.

### 9 · Blok ile görüntü arasında çentik olmaz

Renk bloğunun sınırı ile fotoğrafın kenarı ya **tam hizalanır** ya da
fotoğraf bloğun içine tamamen girer. Aradaki L şeklinde çentik kusurdur.

---

## BÖLÜM III — TİPOGRAFİ

### 10 · İki katman, tek sistem

**Sanat yönü (09A):** tip seçimi, ölçek, başlık kırma, optik ayar.
**QA (09B):** taşma, çarpışma, punto, güvenli alan — model sormaz.

Başlık kırma kararı deterministik kurala bırakılamaz: anlamsal olarak
bozuk ama teknik olarak kusursuz başlıklar üretir.

### 11 · Ölçülebilir eşikler (durdurur)

- Punto ≥ **5,5 pt** (hiçbir metin altına inemez)
- Gövde ≥ **8,5 pt**
- Güvenli alan ihlali = **0** (kesimden 8 mm içeri)
- Metin çarpışması = **0**
- Kullanılan fontun gömülü olması zorunlu

**Uyarır, durdurmaz:** kısa son satır (dul vekili), satır uzunluğu
aşımı, kullanılmayan gömülmemiş font kaydı.

### 12 · PDF üzerinden glif denetimi yapılamaz

Gömülü alt küme fontun cmap'i Unicode değildir. Denendi: gerçek
katalogda **258 yanlış pozitif**. Glif denetimi **kaynak font
dosyaları** üzerinde, dizgiden önce yapılır.

**Ölçüldü:** Metropolis ailesinde `·` (U+00B7) ve `•` (U+2022)
**glifi yok**. Bu karakterler Metropolis ile dizilen metinlerde
otomatik olarak `–` ile değiştirilir.

### 13 · Akış sabit ofsetle hesaplanmaz

**Ölçüldü:** sabit ofsetle konan INCI ve zorunlu uyarı, gövde
beklenenden uzun sardığında üzerine biniyordu — bir sayfada 7 çarpışma.

**Kural:** her blok bir öncekinin **gerçek satır sayısından**
hesaplanır. `blok_yuksekligi_mm()` dizgiden önce ölçer.

### 14 · Tip sistemi bu rolleri taşımak zorundadır

display · başlık ailesi · okunur gövde · kompakt altyazı ·
tabular rakam · **işaretleme/not alanı** · folio.

Not alanı rolü fiziksel satış kataloğunun gereğidir ve atlanamaz.

---

## BÖLÜM IV — RENK

### 15 · Mürekkep varsayılmaz, ölçülen zeminden türetilir

**Ölçüldü:** koyu editoryal fotoğraf zemin olduğunda koyu mürekkep
kullanmak 2,6 kontrast üretiyordu — okunmaz.

`zemin_murekkebi()` sayfanın ölçülen parlaklığından ana ve ikincil
mürekkebi türetir.

### 16 · Metin/görüntü kontrastı ölçülür (durdurur)

**Anayasa'nın en son eklenen kapısı.** Tipografi QA metin-metin
çarpışmasını yakalıyordu ama metnin **görüntü üzerinde** okunup
okunmadığını ölçmüyordu.

- Baskı için eşik: **3,2** (WCAG bağıl kontrast oranı)
- Zemin değişkenliği eşiği: **0,42** — daha değişken zeminde metin
  okunmaz, kontrast ortalaması iyi olsa bile

**Ölçüldü:** ikincil mürekkep 0,44 griyken krem zemin üzerinde 3,0
kontrast veriyordu; 7,5 punto yan metin için baskıda okunmaz. 0,30'a
koyulaştırıldı.

### 17 · Palet üründen türetilir

Sayfa paleti uydurulmaz: baskın ve vurgu renkler fotoğrafın
ölçümünden gelir. Marka mürekkebi sabit kalır; değişken olan zemin ve
vurgudur.

Renk farkı **CIEDE2000** ile Lab uzayında ölçülür. Ürün gövde rengi
ΔE00 ≤ 3,0 · etiket bölgesi ≤ 2,0.

---

## BÖLÜM V — SAYFA SİSTEMİ

### 18 · Format

**210 × 210 mm** + 3 mm taşma = 216 × 216 mm. Güvenli alan kesimden
8 mm içeri. 8 sütun, 4 mm oluk, 4,2 mm taban çizgisi.

**Gerekçe ölçüldü:** diskteki dört gerçek L'CARLIÉ kataloğunun dördü
de 210 × 210 mm. A4 üretim kodunun istisnasıdır.

### 19 · Tutarlı varyasyon

Hedef 30 rastgele sayfa değil, 30 aynı sayfa da değil.

**Kural:** aynı iskelet katalogda iki kez kullanılamaz. Taze iskelet
kalmadıysa tekrar kaçınılmazdır ve **açıkça kayda geçer** — iskelet
havuzu genişletilmelidir.

**Ölçüldü:** 5 pilot 5 farklı iskelet kullanıyor.

### 20 · Yapısal çeşitlilik görsel çeşitlilik değildir

**Ölçüldü:** yeni A4 kataloğunda düzen çeşitliliği 0,97 iken algısal
karma 9 çift sayfayı görsel olarak aynı buluyor. Eski kare katalogda
çeşitlilik 1,000 iken **43 çift** aynı.

**Kural:** tekrar üç sinyalle birlikte ölçülür — düzen imzası, oran
imzası, algısal karma. Tek sinyal yeterli değildir.

### 21 · Kapak ürün sayfası değildir

Kapak künye, INCI ve not alanı taşımaz; kendi iskelet havuzunu
kullanır.

**Ölçüldü:** ürün sayfası iskeletini kapakta kullanmak, koyu editoryal
fotoğraf üzerine künye metni düşürüp üç turda da kontrast kapısından
geçemedi.

### 22 · Her ürün sayfasında not alanı zorunludur

Fiziksel satış aracının geregi. En az 3 satır, etiketli, ölçülü.

---

## BÖLÜM VI — METİN VE MEVZUAT

### 23 · Zorunlu ibare atlanmaz — aşılamaz

Ürün sınıfının gerektirdiği uyarı sayfada basılır. Güneş koruma
ürünlerinde bu madde özellikle denetlenir.

**Uygulama:** `Icerik.uyari` alanı not bloğunun üstüne, akıştan
hesaplanan konuma basılır.

### 24 · Denetlenen fiil değil cümlenin nesnesidir

"cildi destekler" ile "egzamayı destekler" aynı fiili taşır; biri
kozmetik, diğeri tıbbi iddiadır.

Her satış cümlesi bir kaynağa bağlanır: kutu gerçeği veya yayındaki
metin. Bağlanamayan cümle **reddedilir**.

**Pilotlarda uygulandı:** tüm sayfa metinleri `knowledge/30-urun-*.md`
dosyalarındaki doğrulanmış satış cümlelerinden alındı. Uydurulmuş
cümle yoktur.

### 25 · Tekrar dört katmanda ölçülür

birebir · n-gram · kalıp · **anlamsal**. Mevzuat gereği tekrarlanan
uyarılar tekrar sayımına **girmez**.

Anlamsal katman gömme gerektirir; sağlanmazsa `SORAMADIM` döner —
"tekrar yok" değil.

---

## BÖLÜM VII — ÜRETKEN GÖRSEL

### 26 · ComfyUI tasarımcının yerine geçmez

**Kullanılabilir:** arka plan genişletme, destekleyici editoryal
görsel, doku/ortam, kontrollü inpainting/outpainting.

**Kullanılamaz:** mevcut gerçek ürünü yeniden çizmek, etiketi yeniden
üretmek, logoyu yeniden üretmek, TYPE A fotoğrafı gereksiz yere
parçalamak.

### 27 · Final yazı difüzyona çizdirilmez

Tüm tipografi reportlab ile **vektör** dizilir. PNG teslimatı PDF'ten
üretilir — PNG ile PDF birebir aynıdır.

### 28 · Zemin genişletme uydurma değil devam ettirmedir

Fotoğrafın kendi zemin gradyanı ölçülür ve aynı kurala göre dışarı
uzatılır. Difüzyon kullanılmaz.

**Bu pilotta ComfyUI kullanılmadı** — PC-2 erişilemez durumdaydı
(port 8188 kapalı, ölçüldü). Zeminler fotoğrafın kendi ölçülen
gradyanından deterministik üretildi.

---

## BÖLÜM VIII — KARAR VE RET

### 29 · Skor yasağı

"Premium mi? 8/10" karar sayılmaz. Ölçülebilen için **eşik ihlali**,
ölçülemeyen için **GÖZLEM → KANIT → GEREKÇE → KARAR → EYLEM**.

Kanıt paketi iç içe alan adlarını tarar; `skor`, `puan`, `score`,
`rating` içeren alan reddedilir.

### 30 · Sanat yönetmeni tercihi atlama değildir

Sanat yönetmeni bir iskeleti öne sürebilir. Tercih edilen iskelet de
ölü boşluk elemesinden, tekrar kuralından ve tüm kapılardan geçmek
zorundadır. Geçemezse kanıt temelli seçim devreye girer ve bu **kayda
geçer**.

**Ölçüldü:** 5 pilotun 4'ünde sanat yönetmeni tercihi geçti; birinde
kapılar reddetti ve sistem alternatife geçti.

### 31 · Bağımsız eleştirmen brief'i görmez

Eleştirmenin girdisi yalnız render'dır. Her itiraz kusur
taksonomisinden adlandırılır. "Beğenmedim" itiraz sayılmaz.

### 32 · Oylama yok, şiddet kazanır

Üç onay bir HARD_REJECT'i yenemez. Boş karar listesi "geçti" değil
`KANIT_YOK` döner.

### 33 · En fazla 3 tur

Kör sonsuz yeniden deneme yasak. Her turda neyin değiştiği kaydedilir.
Üçüncü turda karar sahibe taşınır.

---

## BÖLÜM IX — BASKI GERÇEĞİ

### 34 · Ekran onayı baskı onayı değildir

Kâğıt, kaplama ve mürekkep bir araya gelmeden renk ve okunabilirlik
bilinemez.

### 35 · Fiziksel prova gerekliliği

Tiraj, fiziksel prova elde tutularak onaylanır: kalemle yazılabiliyor
mu · açık kalıyor mu · ürün renkleri ambalajla uyuşuyor mu.

**Bu kapı hiçbir koşulda otomatikleştirilmez.**

---

## Hâlâ boş bırakılan eşikler

Bunlar V1'de **bilerek** kapatılmadı; ölçüm altyapısı hazır değil.

| madde | eksik eşik | neden |
|---|---|---|
| 5 | saliency payı eşikleri (rol bazlı) | saliency modeli kurulmadı; vekil kullanılıyor |
| 17 | vurgu rengi bütçesi | palet çalışması yapılmadı |
| 25 | anlamsal benzerlik eşiği | gömme hattı katalog metnine bağlanmadı |
| 34 | toplam mürekkep örtüsü | matbaa ve kâğıt seçilmedi; ICC dönüşümü yok |

## V1'in doğrulandığı yer

5 pilot sayfa: `cover`, `hydravie`, `kinesis`, `private-care`,
`daily-care`. Her sayfa için karar kaydı, QA sonucu, köken zinciri ve
kanıt paketi üretildi.
