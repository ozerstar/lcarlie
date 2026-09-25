# 08-copy-editorial -- ilkeler

## Tekrarin uc katmani
1. **Sozcuk tekrari** -- ayni kelime dizisi. n-gram ile yakalanir.
2. **Sozdizimi tekrari** -- ayni cumle iskeleti, farkli kelimeler.
3. **Anlam tekrari** -- farkli kelimeler, ayni vaat. **En tehlikeli
   olan budur ve yalnizca gomme ile yakalanir.**

Mevzuat baskisi yazari sinirli bir vaat kumesine hapseder; yazar
kelimeleri degistirerek n-gram olcumunden kacabilir. 36 urunun
birbirinden ayristigi anlamsal olcum olmadan dogrulanamaz.

## Olculdu (31 urun, 217 satis cumlesi)
- birebir tekrar eden cumle: 1
- 3-gram tekrari: 126 kalip
- "temiz ve kuru" 13 urunde, "nem dengesinin korunmasina" 12,
  "kazanmasina yardimci olur" 10

## Zorunlu tekrar hata degildir
Mevzuat geregi her urunde tekrarlanan uyarilar dogru davranistir.
Tekrar sayimina **girmez**. Bu ayrim yapilmazsa motor dogru davranisi
kusur sayar.

## Olcum kaynagi
Urun dosyasinin tamamini olcmek yaniltir: on bilgi bloklari 36
dosyanin hepsinde aynidir ve motor satis dilini degil bunlari bulur.
Olcum yalnizca satis cumleleri bolumunde yapilir.
