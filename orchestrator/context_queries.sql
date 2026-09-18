-- Static F0-C context profile: decision-v1
-- Parameters are supplied by the repository adapter, never by a model.
SELECT anlik_id, alindi, surum, pencere_7, pencere_30, urun, kanal,
       konusma, veri_kalitesi, eksik_kaynak, kanit_puani, kanit_sinifi
FROM core.kanit_anlik
ORDER BY alindi DESC, anlik_id DESC
LIMIT 20;

SELECT soru_id, hedef, oncelik, beklenen_bilgi_degeri, soru, neden_onemli,
       kaynak_plani, gereken_departmanlar, onay, ureten, durum, olusturma, bekleme
FROM mart.sirket_gundemi
LIMIT 20;

SELECT acik_karar, insan_onayi_bekleyen, uygulandi_olculuyor, sonuclanan,
       reddedilen, ertelenen, sonucsuz, red_team_itirazi, itiraz_alan_karar, toplam
FROM mart.karar_ozet
LIMIT 1;

SELECT tur, anahtar, detay, zaman, yapilacak
FROM mart.acik_isler
LIMIT 20;

SELECT alan, authority, mirror, freshness, current_connection, gap,
       dogrulama_zamani, dogrulama_yontemi, notlar
FROM core.source_authority
ORDER BY alan
LIMIT 40;
