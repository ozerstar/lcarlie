# 00-core -- ilkeler

## 1. Kanit yoksa UNKNOWN
Bir sey olculmediyse "yok" degil "olculmedi"dir. Uc durum birbirinden
ayri tutulur ve asla birbirinin yerine yazilmaz:

| durum | anlami |
|---|---|
| `VERI_YOK` | baktik, kayit yok |
| `SORAMADIM` | bakamadik, arac/erisim yoktu |
| `OKUNAMADI` | baktik, kayit bozuk veya erisilemez |

Bu ayrim yapilmazsa sistem "bulamadim"i "yok" diye rapor eder. Bu hata
bu projede olculmus ve tekrarlanmistir.

## 2. Olculebileni olcme, olculemeyeni uydurma
Olculebilir bir sey modele sorulmaz: pahali ve guvenilmezdir. Yaratici
yargi da sahte matematige cevrilmez: "premium mi? 8/10" olculemeyeni
olculmus gibi gosterir, gerekceyi gizler ve duzeltme icin bilgi vermez.

## 3. Karar kaydinin tek gecerli bicimi
GOZLEM -> KANIT -> GEREKCE -> KARAR -> EYLEM. Dordu de zorunludur;
biri eksikse karar kaydedilemez (`jarvis/katalog_kanit.py` bunu
yapisal olarak zorlar).

## 4. Skor yasagi
Hicbir kanit alani "skor", "puan", "score", "rating" adini tasiyamaz.
Kanit paketi bu adlari tarar ve reddeder.

## 5. Tanimli != uretilebilir
Bir yetenegin tanimli olmasi calistigi anlamina gelmez. Yetenek
kutugunde `implementation_status` bunu ayirir.
