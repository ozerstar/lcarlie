# 12-product-integrity -- ilkeler

## Kanitsiz gecis yoktur
Bu kapinin en onemli kurali: koken kaydi yoksa sonuc **BILINMIYOR**
olur ve **GECMEZ**. Diger kapilarda "kanit yoksa gec" kabul edilebilir;
burada edilemez.

## Yasak islemler (urun pikselinde)
diffusion, inpaint, outpaint_over_product, product_regeneration,
label_regeneration, generative_fill, generative_upscale,
relight_product.

Zincirde bunlardan biri gorunurse **HARD_FAIL**. Veto asilamaz --
sahip bile asamaz; asmak isterse kuralin kendisi degistirilmelidir.

## Geometri
en/boy orani sapmasi esigi %0,5. Perspektif carpitma, skew ve liquify
yasaktir.

## Renk
Govde rengi dE00 <= 3.0, etiket bolgesi dE00 <= 2.0.

## Koken zinciri neyi tasir
varlik kimligi, kaynak dosya SHA-256 ozeti, her adim icin islem adi,
arac, zaman, girdi ve cikti ozeti. Kaynak dosya sonradan degisirse
ozet eslesmez ve kapi durur.
