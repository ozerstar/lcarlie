# 07-color-science -- ilkeler

## RGB'de yakin, algida uzak
Renk kararlari sRGB uzayinda alinamaz. Algisal olarak esit araliklar
icin Lab/LCH kullanilir; renk farki icin **CIEDE2000**.

Uygulamamiz Sharma/Wu/Dalal (2005) yayimlanmis referans kumesinin 21
ciftinde 0.0002 toleransla dogrulanmistir.

## Esikler
- dE00 < 1.0 : egitimsiz gozle ayirt edilemez
- dE00 ~ 2-3 : dikkatli bakista fark edilir
- Urun govde rengi icin esik: **3.0**
- Etiket bolgesi icin: **2.0** (daha siki)

## Baski gercegi
Kaplamali kagitta Avrupa ofseti icin guncel standart **PSO Coated v3**
(FOGRA51 karakterizasyonu, ISO 12647-2:2013). Kaplamasiz forma
kullanilirsa ayri profil gerekir.

Olculdu: mevcut uretim **RGB PDF** cikariyor; ICC output intent yok.

## Kapsam disi (bu fazda yazilmadi)
CMYK ayrimi, toplam murekkep ortusu (TAC), siyah uretimi (GCR/UCR),
overprint ve trapping. Bunlar prepress katmanina aittir.
