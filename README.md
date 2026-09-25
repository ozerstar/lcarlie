# n8n workflow anlik goruntuleri

Bu dal **yetim**dir: kod dallariyla ortak atasi yoktur ve onlarla
birlestirilmez. Icerigi `/opt/lcarlie/n8n-wf-yedek.sh` tarafindan uretilir.

## Neden var

Kod 24.09.2026'da GitHub'a tasindi, workflow'lar tasinmadi. Gecelik sifreli
yedek `workflows.json` tasidigi icin **geri yukleme** zaten mumkundu; eksik
olan **degisiklik izi**ydi: kim neyi ne zaman degistirdi sorusunun cevabi
hicbir yerde yoktu.

## Nasil calisir

`lcarlie-n8n-wf-yedek.timer` her gun 03:50'de betigi kosturur:
`n8n export:workflow --all --pretty --separate` -> `workflows/` -> degisiklik
varsa commit -> GitHub'a push.

`export` salt okunurdur; workflow'larin aktifligine dokunmaz. Yayina alma
yolu ayridir ve `/opt/lcarlie/n8n-yayinla.sh` uzerinden yurur.

## Bos export commit'lenmez

Disa aktarim sifir dosya dondururse betik commit YAPMAZ ve alarm uretir.
Aksi halde bos bir kosu, gecmisteki dogru kopyayi "silinmis" gosterirdi.
