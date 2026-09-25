# 14-prepress -- ilkeler

## Preflight kontrol listesi
tasma 3 mm tam / guvenli alan ihlali 0 / ICC output intent gomulu /
efektif DPI hedef ustunde ve **buyutmesiz** / tum kullanilan fontlar
gomulu ve alt kume / toplam murekkep ortusu esik alti / cilt payi
formata uygun / PDF/X uyumlu.

## Standart uyumu matbaa kabulu degildir
Matbaanin kendi sartnamesi standarttan once gelir. Standart uyumlu ama
matbaanin kabul etmedigi dosya ise yaramaz. GWG 2022 ortak bir taban
verir; matbaaya ozel kurallar ustune eklenir.

## Bugunku durum -- olculdu
- Cikti **RGB**; ICC output intent yok
- Tasma sayfa kutusunda var (216x303 = 210x297 + 3 mm), ancak guvenli
  alan denetimi kodda **yok**
- Efektif DPI raporlaniyor ama **buyutulmus pikseli sayiyor**
- Toplam murekkep ortusu hic hesaplanmiyor
- PDF/X dogrulamasi yok

## Bu fazda yazilmayanlar
CMYK ayrimi, TAC hesabi, overprint/trapping denetimi, PDF/X
dogrulayici entegrasyonu. Kapsam disi birakildi ve acik risk olarak
kaydedildi.
