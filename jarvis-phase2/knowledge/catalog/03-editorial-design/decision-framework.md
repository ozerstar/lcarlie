# 03-editorial-design -- karar cercevesi

## Sayfa sistemi kabul edilir mi
1. Grid formattan turetildi mi, yoksa onceki formattan mi tasindi?
2. Duzen ailesi kac varyant? Hepsi ayni grid'den mi turedi?
3. Ardisik iki sayfanin imzasi ayni mi? (deterministik denetim)
4. Algisal karma gorsel tekrar gosteriyor mu? (imzadan bagimsiz)
5. Her sayfa tipi icin zorunlu ogeler yerinde mi?
6. Her urun sayfasinda not alani var mi ve olcusu yeterli mi?

## Kontrollu kural bozma
Grid ancak bolum acilisinda ve gerekceli olarak bozulur. Her sayfada
bozulursa grid yok demektir; hic bozulmazsa katalog sablon hissi verir.
