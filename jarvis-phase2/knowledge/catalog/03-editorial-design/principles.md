# 03-editorial-design -- ilkeler

## Tutarli varyasyon
Hedef 30 rastgele sayfa degil, 30 ayni sayfa da degil. Varyasyon
grid'i **bozarak** degil grid'i **farkli kullanarak** uretilir.

Olculdu: mevcut sistemde `ACILIS_DUZENLERI` uc varyant tanimliyor ve
33 sayfaya dagitiliyor. Duzen imzasi cesitliligi 0.97 gorunuyor ama
algisal karma 9 cift sayfayi **gorsel olarak ayni** buluyor. Yapisal
cesitlilik gorsel cesitlilik demek degildir.

## Duzen imzasi
Her sayfa icin bloklarin grid hucrelerine oturan konum/olcu dizisi +
gorsel/metin/bosluk oranlari + odak sayisi. Iki kural:
- Ardisik iki sayfanin imzasi ayni olamaz (deterministik).
- Katalog geneli imza cesitliligi esik ustunde olmali.

Imza yapisal, algisal karma gorseldir; **ikisi birlikte gerekir**.

## Ritim
Bilgi yogunlugu bes kademeye ayrilir. Ardisik uc sayfa ayni kademede
olmamalidir. Olculdu: logaritmik olcege gecmeden once 33 sayfanin
25'i ayni kademedeydi ve olcum ayirt edici degildi.

## Sayfa tipleri
urun / icerik (INCI) / ritual / karsilastirma / teknik / bolum acilisi
/ hero / fiyat. Her tipin kendi bilgi mimarisi ve zorunlu ogeleri var.
Olculdu: icerik, ritual ve karsilastirma sayfa tipleri **bugun yok**.

## Cilt payi
Ic kenar dis kenardan farkli hesaplanir. Olculdu: mevcut mimaride
cilt payi tanimi **yok** -- yalnizca 5 mm guvenli alan var.

## Not alani
Fiziksel satis katalogunun geregi: her urun sayfasinda yazilabilir bir
alan tanimlanir ve olculur. Bugun yok.
