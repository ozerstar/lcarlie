# L'CARLIÉ KATALOG TASARIM ANAYASASI — TASLAK

> **DURUM: TASLAK. ÜRETİM KAPISI DEĞİLDİR.**
> Bu belge FAZ −1B sonunda üretildi ve henüz hiçbir üretim akışına
> bağlanmadı. FAZ −1C (Constitution Review & Calibration) sonrasında
> kural haline gelir.

---

## Yazım ilkesi

Bu anayasa **koşullu tasarım ilkeleri** yazar, mutlak kurallar değil.

Şunun gibi maddeler bilerek **yazılmamıştır**:

- ~~"ürün her zaman %50 büyük olsun"~~
- ~~"her zaman bol boşluk kullan"~~
- ~~"başlık her zaman sol üstte"~~
- ~~"premium = bej"~~
- ~~"ürün hiçbir zaman crop edilmez"~~

Böyle bir kural yeni bir şablon üretir ve tam olarak çözmeye çalıştığı
sorunu yaratır. Her madde şu biçimdedir: **koşul → değerlendirme →
ölçülebilir kısım → kimin kararı.**

Ölçülebilen yerde ölçüm, ölçülemeyen yerde uzman yargısı. İkisi
birbirinin yerine geçmez.

---

## 1 · Marka görsel felsefesi

Dermokozmetik kategorisi bir gerilimdir: **bilimsel güven** ile **lüks
duygusu** aynı sayfada yaşamak zorundadır. Fazla klinik olursa arzu
ölür, fazla lüks olursa eczacı güvenmez.

Bu denge her sayfada yeniden kurulur; tek bir "marka tonu" ayarlayıp
geçmek mümkün değildir. Bir sayfanın hangi tarafa çekildiği bilinçli
olmalı ve gerekçesi yazılabilmelidir.

**Karar:** C02 sınırlar, C07 uygular, C01 bütünlüğü denetler.

## 2 · Ürün fotoğrafı hiyerarşisi

Ürün görseli tek tip varlık değildir. Dört sınıf vardır ve sınıf,
yapılabilecek işlemleri belirler — tersi değil.

Bir görselin sınıfı, o görselle *ne yapmak istediğimizden* bağımsız
olarak ölçülür. "Bu sahneye ihtiyacım var" bir görseli TYPE C yapmaz.

**Karar:** C07A ölçer ve sınıflar; ihlalde HARD_REJECT.

## 3 · Varlık sınıfı kuralları

| sınıf | varsayılan | koşul |
|---|---|---|
| **A** editoryal | **DOKUNMA** | Kompozisyon, ışık ve arka plan zaten tasarlanmış |
| **B** stüdyo | genişletilebilir | Profesyonel çekim, sahne nötr |
| **C** packshot | kompozit edilebilir | İzole ürün |
| **D** yetersiz | **ÜRETİM DURUR** | Hedef yerleşim için kaynak yetmiyor |

TYPE A'da yasak: arka plan kaldırma, otomatik ürüne kırpma, ürün veya
etiket yeniden üretimi, arka plan değiştirme, geometri değişikliği.

**Gerekçe (ölçülmüş):** kesim adımı basılabilir ölçünün ~%75'ini
götürüyor — kaynak medyanı 106 mm, kesim medyanı 25 mm (300 DPI).

## 4 · Fotoğraf → düzen ilkesi

Akış **ŞABLON → FOTOĞRAF** değil, **FOTOĞRAF → ANALİZ → SANAT YÖNÜ →
DÜZEN** olmalıdır.

Düzen, fotoğrafın metin güvenli bölgelerinden türetilir. Fotoğrafı
önceden tanımlı bir kutuya sığdırmak, iyi fotoğrafı kötü kullanmanın
en yaygın yoludur.

**Koşul:** TYPE A ve B görsellerde bu zorunludur. TYPE C'de sahne
tasarlanabilir, ama o zaman sahne de bir fotoğraftır ve aynı kural
ona uygulanır.

## 5 · Ürün baskınlığı

Baskınlık boyut değildir. Sabit bir yüzde kuralı **yasaktır**.

Baskınlığı belirleyen: fiziksel ölçü, görünür alan, **kontrast (en
güçlü tek faktör)**, konum, izolasyon, keskinlik, çevre yoğunluğu,
saliency, aydınlatma, önplan baskınlığı, kadraj, kenar etkileşimi,
arka plan rekabeti.

**Değerlendirme:** önce sayfanın rolü belirlenir (HERO / ANLATI /
KATALOG / DETAY / SESSİZ), sonra baskınlık profilinin o role uyup
uymadığına bakılır.

**Ret koşulu:** sayfa rolü HERO veya KATALOG iken ürünün saliency payı
eşiğin altındaysa — ürün büyük olsa bile.

## 6 · Kırpma felsefesi

Kırpma ürün kimliğini yok ediyorsa başarısızdır. Ancak kasıtlı aşırı
kadraj görsel baskınlık, ölçek kontrastı veya editoryal gerilim
üretiyorsa başarılıdır.

Düşük kırpma korunumu **otomatik olarak kötü değildir**: bilinçli
editoryal kırpma da düşük korunum üretir. Ölçüm ile yargı ayrı tutulur.

**Ölçülebilir kısım:** korunum oranı, çıktı piksel ölçüsü, en/boy
değişimi, ürünün tanınabilirliği (etiket okunur mu).
**Yargı:** kırpmanın gerilim mi kaza mı ürettiği.

## 7 · Negatif alan

Boşluk kendiliğinden premium değildir.

## 8 · Aktif ve ölü boşluk

**Aktif boşluk** bir iş yapar: ayırır, vurgular, nefes verir.
**Ölü boşluk** hiçbir iş yapmaz ve bir **kusurdur**.

Ölü boşluğun ölçülebilir imzası: büyük bitişik boş bölge + düşük
saliency + kasıtlılık işareti yokluğu (tipografik veya kompozisyonel).

"Lüks kısıtlama" gerekçesiyle savunulamaz. Bir boşluğun işi
sorulduğunda cevap verilemiyorsa o boşluk ölüdür.

**Ölçülmüş örnek:** eski kare katalogda alt yarısı boş, yapısal olarak
birbirinin aynı iki metin sayfası bulundu (s7 ve s9, algısal karma
mesafesi 6).

## 9 · Görsel gerilim

Gerilim yoksa sayfa ölüdür; fazlaysa huzursuzdur. Gerilim ölçülemez;
kenar mesafesi, ölçek farkı ve asimetri ölçülebilir ve gerilimin
*girdisi*dir.

**Karar:** C07. Ölçüm karar vermez.

## 10 · Optik denge

Geometrik merkez algısal merkez değildir. Sayfayı ortalamak denge
üretmez; ağırlık merkezini bilinçli konumlandırmak üretir.

Açılım (spread) tek kompozisyondur: iki sayfa birlikte dengelenir,
ayrı ayrı değil.

## 11 · Ölçek kontrastı

Editoryal enerjinin ana kaynağıdır. Her şey orta boy ise sayfa
"katalog" görünür — istenen bu değildir.

**Ölçülebilir:** alan oranları dağılımının genişliği.
**Koşul:** ölçek kontrastı her sayfada gerekmez; bölüm içinde ritmik
olarak dağıtılır.

## 12 · Sayfa hiyerarşisi

Her sayfada tek bir birincil odak olur. İki eşit güçlü odak gözün
gidip gelmesine yol açar ve hiyerarşiyi yok eder.

**Ölçülebilir:** saliency tepe sayısı ve tepeler arası genlik farkı.

## 13 · Açılım hiyerarşisi

Açılımın iki yarısı ya dengelenir ya da **kasıtlı olarak** dengesiz
bırakılır. Kasıtsız dengesizlik kusurdur.

Cilt payı boyunca süren görsel, konunun tam ortadan bölünmemesini
gerektirir.

## 14 · Sayfa ritmi

Ardışık üç sayfa aynı yoğunluk kademesinde olamaz.

**Ölçülmüş:** yeni A4 kataloğunda 6, eski kare katalogda 43 böyle
dizi var. Eski katalog bu ölçütte belirgin biçimde daha monoton.

## 15 · Katalog temposu

Katalog bir dizidir: giriş, gelişme, doruk, dinlenme. Bölüm geçişleri
sayfa çevrilmeden anlaşılmalıdır.

**Koşul:** 52 sayfalık bir katalogda en az 3 doruk ve 3 dinlenme anı
beklenir; bu bir formül değil, ritmin gözlemlenebilir olması şartıdır.

## 16 · Hero / sessiz / teknik sayfa ritmi

- **HERO:** bölüm başına en fazla 1.
- **SESSİZ:** kasıtlılık işareti taşımalı — yoksa boş sayfadır.
- **TEKNİK:** yoğunluk yüksek olabilir; okunabilirlik eşikleri
  gevşetilemez.

Her sayfa hero ise hiçbiri hero değildir.

## 17 · Grid disiplini

Grid formattan türetilir, önceki formattan taşınmaz.

**Ölçülebilir:** taban çizgisi uyumu, sütun hizalaması, kenar ve
oluk ölçüleri, cilt payı.

## 18 · Kontrollü kural bozma

Grid ancak gerekçeli olarak bozulur — tipik olarak bölüm açılışında.

Her sayfada bozulursa grid yoktur. Hiç bozulmazsa katalog şablon hissi
verir. İkisi de kusurdur.

**Ölçülebilir:** grid dışı yerleşim sayısı / toplam sayfa.

## 19 · Tipografi sanat yönü

Başlık kırma, ölçek seçimi, optik hizalama ve tip–görsel ilişkisi
yaratıcı kararlardır ve deterministik kurala bırakılamaz.

**Gerekçe:** "GÜNEŞ KORUYUCU / KREM SPF 50+ YÜKSEK / KORUMA"
tipografik olarak kusursuz, anlamsal olarak bozuktur — ve QA bunu
ihlal saymaz.

Tip sistemi şu rolleri taşımak zorundadır: display, başlık ailesi,
okunur gövde, kompakt altyazı, tabular rakam, **işaretleme/not alanı**,
folio.

## 20 · Tipografi QA

Ölçülebilir ihlaller uzman yargısına bırakılmaz ve gevşetilemez.

**Durdurur:** punto < 5,5 pt · güvenli alan ihlali · metin çarpışması ·
kullanılan fontun gömülmemiş olması · kaynak fontta Türkçe glif eksiği.

**Uyarır:** kısa son satır (dul vekili) · satır uzunluğu aşımı ·
kullanılmayan gömülmemiş font kaydı.

**Yapılamaz:** PDF'e gömülü alt küme font üzerinden glif denetimi.
Ölçüldü: 258 yanlış pozitif üretir.

## 21 · Renk yönü

Renk kararları algısal uzayda (Lab/LCH) alınır, sRGB'de değil. Renk
farkı CIEDE2000 ile ölçülür.

**Eşikler:** ürün gövde rengi ΔE00 ≤ 3,0 · etiket bölgesi ≤ 2,0.

Vurgu rengi bütçelidir: bir açılımda kaç farklı vurgu rengi
kullanılabileceği tanımlanır.

## 22 · Botanik–bilim dengesi

Bitkisel içerik bir "doğal ürün" iddiası değildir. Doğal olanı bilimin
karşıtı gibi sunmak marka konumuna aykırıdır.

Görsel dilde de geçerli: bitki görselleri ürünü "doğal" ilan etmez,
formülasyonun içeriğini anlatır.

## 23 · Lüks kısıtlama

Kısıtlama az öğe ve düşük gürültüdür — boşluk değil.

**Ölçülebilir:** sayfadaki öğe sayısı, palet genişliği, tipografik
stil sayısı, vurgu rengi sayısı.

**Ölçülmüş:** yeni A4 kataloğunda sayfa başına medyan 52 öğe var;
eski kare katalogda 18. Bu ölçütte eski katalog belirgin biçimde daha
kısıtlı.

## 24 · Kategori ayrışması

36 ürün birbirinden ayrışmalıdır. Ayrışma hem metinde hem görselde
ölçülür.

**Metin:** birebir / n-gram / kalıp / anlamsal tekrar.
**Görsel:** düzen imzası + oran imzası + algısal karma.

**Ölçülmüş:** 31 ürünün satış metninde 126 adet 3-gram kalıbı ≥3
üründe geçiyor.

## 25 · Görsel–tipografi ilişkisi

Tipografi görselin üstüne "atılmaz"; görselin kontrast ve saliency
haritasından türeyen güvenli bölgelere yerleştirilir.

**Ölçülebilir:** metin bölgesindeki kontrast, saliency ve doku.

## 26 · Ürün bütünlüğü

Gerçek ürün, ambalaj, etiket ve logo pikselleri **hiçbir koşulda**
üretken modelden geçemez.

Köken kaydı yoksa sonuç BİLİNMİYOR'dur ve **geçmez**. Bu kapıda
"kanıt yoksa geç" geçersizdir.

**Bu madde aşılamaz.** Sahip bile aşamaz; aşmak isterse kuralın
kendisi değiştirilmelidir.

## 27 · AI üretim sınırları

ComfyUI ve benzeri üretken araçlar yalnızca **sahne ve arka plan**
üretir.

Üretilen görselde ürün, logo veya metin bulunamaz. Negatif istem bunu
garanti etmez (ölçüldü) — çıktı denetlenir.

**Ölçülebilir:** nesne tespiti, OCR, köken zinciri.

## 28 · Tekrar sınırları

Ardışık iki sayfanın düzen imzası aynı olamaz.

Katalog geneli düzen çeşitliliği eşik üstünde olmalıdır — **ancak**
yapısal çeşitlilik görsel çeşitlilik demek değildir.

**Ölçülmüş:** yeni katalogda düzen çeşitliliği 0,97 iken algısal karma
9 çift sayfayı görsel olarak aynı buluyor. Eski katalogda çeşitlilik
1,000 iken 43 çift aynı. **Tek sinyal yeterli değildir.**

## 29 · Tutarlı varyasyon

Hedef 30 rastgele sayfa değil, 30 aynı sayfa da değil.

Varyasyon grid'i **bozarak** değil grid'i **farklı kullanarak**
üretilir. Düzen ailesi tek bir grid'den türeyen en az 6 varyant
içerir.

## 30 · Metin hiyerarşisi

Her sayfa tek bir ana mesaj taşır. İkincil bilgi ikinci kademededir.

**Koşul:** teknik ve karşılaştırma sayfaları istisnadır; orada bilgi
yoğunluğu amaçtır, ama okunabilirlik eşikleri gevşetilemez.

## 31 · Bilimsel güvenilirlik

Güven yalnız metinle kurulmaz. Tabular rakam, düzgün tablo dizgisi ve
tutarlı grid, içerikten bağımsız olarak "bu firma işini biliyor"
mesajı taşır.

Kaynaksız yüzde, kanıtsız üstünlük ve mucize dili kategoriyi zedeler.

## 32 · Mevzuat güvenliği

Denetlenen fiil değil **cümlenin nesnesidir**.

Her satış cümlesi bir kaynağa bağlanır: kutu gerçeği veya yayındaki
metin. Bağlanamayan cümle **reddedilir**.

Zorunlu uyarılar tekrar kusuru sayılmaz.

**Bu madde aşılamaz.**

## 33 · Baskı gerçeği

Ekran onayı baskı onayı değildir.

Kâğıt, kaplama ve mürekkep bir araya gelmeden renk ve okunabilirlik
**bilinemez**.

Efektif DPI büyütülmüş pikselden ölçülemez. Büyütme, geçme sebebi
olamaz.

Matbaanın kendi şartnamesi standarttan önce gelir.

## 34 · Fiziksel prova gerekliliği

Tiraj, **fiziksel prova elde tutularak** onaylanır.

Provada doğrulanacaklar: kalemle yazılabiliyor mu · açık kalıyor mu ·
ürün renkleri ambalajla uyuşuyor mu · elde ve masada nasıl duruyor.

**Bu kapı hiçbir koşulda otomatikleştirilmez.**

## 35 · Yaratıcı ret ilkeleri

Ret gerekçesi kusur taksonomisinden adlandırılır: tekrar, klişe, küçük
ürün, ölü boşluk, zayıf hiyerarşi, yapay zekâ görünümü, kadraj kazası,
ton dengesizliği, açılım dengesizliği.

"Beğenmedim" itiraz sayılmaz. "Premium mi? 8/10" karar sayılmaz.

Karar kaydının tek geçerli biçimi:
**GÖZLEM → KANIT → GEREKÇE → KARAR → EYLEM.**

Ret çözümlemesinde **oylama yoktur**: en şiddetli karar kazanır. Üç
onay bir HARD_REJECT'i yenemez.

Üçüncü turda karar sahibe taşınır.

---

## Bu taslakta bilerek BOŞ bırakılanlar

Aşağıdaki eşikler FAZ −1C'de, gerçek ölçümlerle doldurulacaktır.
Şimdi tahminle yazmak, ölçümü tahmine uydurmak olurdu.

| madde | eksik eşik | neden şimdi yazılmadı |
|---|---|---|
| 5 | saliency payı eşikleri (rol bazlı) | saliency motoru henüz kurulmadı |
| 11 | ölçek kontrastı alt sınırı | kalibrasyon verisi yok |
| 14 | yoğunluk kademe sınırları | benchmark ile kalibre edilecek |
| 21 | vurgu rengi bütçesi | palet çalışması yapılmadı |
| 24 | anlamsal benzerlik eşiği | gömme hattı katalog metnine bağlanmadı |
| 28 | düzen çeşitliliği alt sınırı | iki katalog karşılaştırması yeterli örnek değil |
| 33 | toplam mürekkep örtüsü eşiği | matbaa ve kâğıt seçilmedi |

## Bu taslağın dayandığı ölçümler

Tüm sayısal iddialar 25.09.2026 tarihli ölçümlerdir ve
`evidence/katalog-benchmark.json` ile
`knowledge/catalog/*/items.json` içinde kaynaklarıyla birlikte
kayıtlıdır.
