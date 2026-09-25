# 06-typography -- ilkeler

## Iki katman, tek sistem
**09A yaratici:** tip secimi, olcek, baslik kirma, optik ayar.
**09B deterministik:** tasma, carpisma, punto, satir uzunlugu, guvenli alan.

Ayrim gereklidir cunku baslik kirma kararini deterministik kurala
birakmak anlamsal olarak bozuk basliklar uretir ve QA bunu ihlal
saymaz -- teknik olarak ihlal degildir.

Ornek: "GUNES KORUYUCU / KREM SPF 50+ YUKSEK / KORUMA" tipografik
olarak kusursuz, anlamsal olarak bozuktur.

## Tip sisteminin tasimasi gereken roller
display / baslik ailesi (cok agirlikli) / okunur govde / kompakt
altyazi / tabular rakam / **isaretleme-not alani** / folio.

Olculdu: mevcut sistemde 10 stil tanimli ama rol ayrimi yok ve
**not/isaretleme rolu hic yok**.

## PDF uzerinden glif denetimi YAPILAMAZ
Olculdu (25.09.2026): PDF'e gomulu alt kume fontun cmap'i Unicode
degildir. Metropolis-Medium alt kumesi 101 kod tasiyor ama kodlar
1,2,3... diye yeniden numaralanmis; `ord('u')` cmapte yok. Hem
fontTools hem `pymupdf.Font.has_glyph` False donuyor -- oysa sayfa
render edildiginde Turkce karakterler **dogru** basiliyor.

Denendi: gercek katalogda **258 yanlis pozitif**. Glif denetimi
KAYNAK font dosyalari uzerinde, dizgiden ONCE yapilir.

## Kullanilmayan font uretimi durdurmaz
Olculdu: Helvetica 33 sayfanin kaynak listesinde ama hicbir metin
span'i kullanmiyor. Uyaridir, engel degil.

## Turkce
`I/i` ve `İ/ı` ayrimi kucuk harfe cevirmede ozel islem ister. Kesme
isareti (') tirnak (') ile karistirilmaz.
