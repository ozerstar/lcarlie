# 11-retouch-compositing -- ilkeler

## Temas golgesi olmayan urun havada durur
Kesilmis urun yeni bir yuzeye konurken temas noktasinda golge
uretilmelidir. Yoksa izleyici bunu adlandiramaz ama sahtelik hisseder.

## Isik yonu uyumu
Sahne ve urun farkli yonden aydinlatilmissa kompozit "yapistirilmis"
gorunur. Olculebilir: parlaklik gradyaninin ana ekseni.

## Kenar kalitesi
Alfa kenarinda halo ve fringe artefakti aranir. Maskeyi asiri
sertlestirmek urun kenarini yer -- bu olculmus bir hatadir ve
gorsel-kompozit.py icinde not edilmistir.

## Model secimi
Mevcut kesim `u2net` ile yapiliyor; rembg'in en eski modeli.
`isnet-general-use` ve `birefnet-general` kenar kalitesinde belirgin
ustundur ve **ayni pakette** mevcuttur -- yeni bagimlilik gerekmez.

## Cam ve seffaf ambalaj
Seffaf urunlerde arka plan gecirgenligi korunmalidir; duz alfa maskesi
cam urunu opak plastige cevirir.
