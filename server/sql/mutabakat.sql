-- =============================================================================
-- L'CARLIE - MUTABAKAT VE DEGISMEZ KONTROLLERI  (CR-008)
--
-- 🔴 NEDEN VAR:  16.09.2026 denetiminde, kalem cirosunun siparis cirosundan
--    %18,8 sisik oldugu ortaya cikti (kalem indirimi hic okunmuyordu).
--    Hata AYLARCA gorunmedi cunku KIMSE IKI RAKAMI YAN YANA KOYMADI.
--    Buradaki testler tam olarak bunu yapar: birbirinden turemis iki sayinin
--    tutup tutmadigini sorar.
--
-- 🔴 SABIT SAYIYA CAKILMAZ.  raw-dogrula.sql "37 siparis olmali" der ve
--    38. siparis geldigi an kirmizi yanar. Her zaman kirmizi yanan test,
--    bakilmayan testtir. Buradaki kontroller ILISKISELDIR: veri buyudukce
--    dogru kalirlar.
--
-- Cikis: her satir SUCCESS / FAILED / UYARI
-- Kullanim: docker exec -i lcarlie-postgres psql -U n8n -d n8n -f mutabakat.sql
-- =============================================================================
\pset footer off

\echo '=== A) CIRO MUTABAKATI ==='
-- Kalem toplami ile siparis toplami BIREBIR tutmali.
SELECT 'kalem net toplami = siparis toplami' AS kontrol,
       to_char(k.net,'FM999999990.00') AS kalem,
       to_char(s.top,'FM999999990.00') AS siparis,
       CASE WHEN round(k.net,2) = round(s.top,2) THEN 'SUCCESS'
            ELSE 'FAILED (fark: ' || to_char(k.net-s.top,'FM999999990.00') || ')' END AS durum
  FROM (SELECT sum(net_toplam) AS net FROM raw.wix_order_item) k,
       (SELECT sum(toplam) AS top FROM raw.wix_order) s;

-- Siparis bazinda: kac sipariste tutmuyor
SELECT 'tutmayan siparis sayisi' AS kontrol, count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM (SELECT w.siparis_id
          FROM raw.wix_order w JOIN raw.wix_order_item i ON i.siparis_id=w.siparis_id
         GROUP BY w.siparis_id, w.toplam
        HAVING round(sum(i.net_toplam),2) <> round(w.toplam,2)) t;

\echo ''
\echo '=== B) SINIFLANDIRMA BUTUNLUGU ==='
-- 🔴 Her siparis TAM BIR tutar kolonuna girmeli: ne hicbirine, ne ikisine.
SELECT 'her siparis tam bir tutar kolonunda' AS kontrol,
       count(*)::text AS hatali, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM mart.siparis
 WHERE (ciro_dogrulanmis IS NOT NULL)::int + (ciro_beyan_edilmis IS NOT NULL)::int
     + (tutar_bekleyen IS NOT NULL)::int + (tutar_bilinmiyor IS NOT NULL)::int
     <> CASE WHEN ciro_sinifi = 'IPTAL' THEN 0 ELSE 1 END;

SELECT 'siniflandirilamayan siparis' AS kontrol,
       count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'UYARI' END AS durum
  FROM mart.siparis WHERE ciro_sinifi = 'BILINMIYOR';

SELECT 'yonu bilinmeyen gonderi' AS kontrol,
       count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'UYARI' END AS durum
  FROM mart.gonderi WHERE sinif = 'YON_BILINMIYOR';

-- 🔴 ELLE_SATIS CIFT SAYIM KONTROLU (sahip kurali 16.09.2026).
--    Kapida odemeli + Wix kaydi olmayan gonderi WhatsApp/telefon satisi
--    sayiliyor ve cirosu ayrica toplaniyor. Eger bir gonderi hem Wix
--    siparisiyle eslesip hem ELLE_SATIS sayilirsa ayni para IKI KEZ
--    sayilir ve ciro sisirilir - tam da bu projenin en pahali hatasinin
--    (kalem indirimi) tersi yonu.
SELECT 'ELLE_SATIS''in Wix karsiligi yok' AS kontrol,
       count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED (cift sayim)' END AS durum
  FROM mart.gonderi WHERE sinif='ELLE_SATIS' AND siparis_id IS NOT NULL
UNION ALL
-- Elle satis cirosu YALNIZ ELLE_SATIS sinifindan gelmeli.
SELECT 'elle ciro yalniz ELLE_SATIS sinifinda', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.gonderi
 WHERE (elle_ciro_tahsil IS NOT NULL OR elle_ciro_bekleyen IS NOT NULL)
   AND sinif <> 'ELLE_SATIS';

\echo ''
\echo '=== C) SATIR SAYISI KORUNUYOR MU (JOIN cogalmasi/kaybi) ==='
SELECT 'mart.siparis = raw.wix_order' AS kontrol,
       (SELECT count(*) FROM mart.siparis)::text || ' / ' || (SELECT count(*) FROM raw.wix_order)::text AS deger,
       CASE WHEN (SELECT count(*) FROM mart.siparis) = (SELECT count(*) FROM raw.wix_order)
            THEN 'SUCCESS' ELSE 'FAILED' END AS durum
UNION ALL
SELECT 'mart.siparis_kalem = raw.wix_order_item',
       (SELECT count(*) FROM mart.siparis_kalem)::text || ' / ' || (SELECT count(*) FROM raw.wix_order_item)::text,
       CASE WHEN (SELECT count(*) FROM mart.siparis_kalem) = (SELECT count(*) FROM raw.wix_order_item)
            THEN 'SUCCESS' ELSE 'FAILED' END
UNION ALL
SELECT 'mart.gonderi = raw.bk_shipment',
       (SELECT count(*) FROM mart.gonderi)::text || ' / ' || (SELECT count(*) FROM raw.bk_shipment)::text,
       CASE WHEN (SELECT count(*) FROM mart.gonderi) = (SELECT count(*) FROM raw.bk_shipment)
            THEN 'SUCCESS' ELSE 'FAILED' END;

\echo ''
\echo '=== D) ZAMAN SERISI DEGISMEZLERI (maliyet versiyonlama) ==='
-- 🔴 Versiyonlamanin tum degeri bu uc sarta bagli.
SELECT 'sifir uzunluklu donem yok' AS kontrol, count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM core.urun_maliyet WHERE gecerli_bitis IS NOT NULL AND gecerli_bitis <= gecerli_baslangic
UNION ALL
SELECT 'ust uste binen donem yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.urun_maliyet a JOIN core.urun_maliyet b
    ON a.urun_id = b.urun_id AND a.maliyet_id < b.maliyet_id
   AND a.gecerli_baslangic < coalesce(b.gecerli_bitis,'infinity'::timestamptz)
   AND b.gecerli_baslangic < coalesce(a.gecerli_bitis,'infinity'::timestamptz)
UNION ALL
SELECT 'urun basina en fazla 1 aktif kayit', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM (SELECT urun_id FROM core.urun_maliyet WHERE gecerli_bitis IS NULL
         GROUP BY urun_id HAVING count(*) > 1) t;

\echo ''
\echo '=== E) PII SIZINTISI ==='
SELECT 'BasitKargo ham PII temiz' AS kontrol, count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM raw.bk_shipment
 WHERE ham#>>'{recipient,name}' IS NOT NULL OR ham#>>'{recipient,phone}' IS NOT NULL
    OR ham#>>'{recipient,address}' IS NOT NULL OR ham#>>'{sender,phone}' IS NOT NULL
UNION ALL
-- 🔴 Yukleme gunlugu AYRI bir maruziyet yuzeyidir: hata mesajlari oraya
--    dusuyor ve mesajda ham gövde tasinabiliyordu.
-- 🔴 DESEN KELIME SINIRLI OLMALI.  Ilk surum `(\+90|0)?5[0-9]{9}` idi ve
--    reklam hesabi kodu 560782561026922'nin ICINDEKI 10 haneyi telefon
--    sandi -> test ilk calismada YANLIS POZITIF verdi. Yanlis pozitif veren
--    test, bakilmayan testtir; gercek sizintiyi de gizler. \m ve \M
--    (kelime basi/sonu) ile yalniz TAM telefon numarasi eslesir.
SELECT 'yukleme gunlugunde e-posta/telefon deseni yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.yukleme_log
 WHERE mesaj ~ '[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    OR mesaj ~ '\+905[0-9]{9}\M'
    OR mesaj ~ '\m05[0-9]{9}\M'
    OR mesaj ~ '\m5[0-9]{9}\M';

\echo ''
\echo '=== F) KAYIP VERI ==='
SELECT 'tarihi cozulemeyen siparis' AS kontrol, count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM raw.wix_order WHERE olusturma IS NULL
UNION ALL
SELECT 'tarihi cozulemeyen gonderi', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.bk_shipment WHERE olusturma IS NULL
UNION ALL
SELECT 'hayalet foreignCode', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.bk_shipment b WHERE b.foreign_code IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM raw.wix_order w WHERE w.siparis_id=b.foreign_code)
UNION ALL
SELECT 'kimliksiz musteri (yetim)', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.customer c
 WHERE NOT EXISTS (SELECT 1 FROM core.customer_identity ci WHERE ci.customer_id=c.customer_id)
UNION ALL
-- 1 Ekim sonrasi her siparisin kanonik musterisi olmali.
SELECT 'olcumde musterisiz siparis', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis WHERE olcumde AND customer_id IS NULL;

\echo ''
\echo '=== G) HARCAMA TEKILLIGI ==='
-- 🔴 PK'da 'kaynak' oldugu icin ayni gun/kampanya META_API ve ELLE olarak
--    IKI satir tasiyabilir; view'lar bunlari TOPLAR ve harcama iki katina cikar.
SELECT 'ayni gun+kampanya icin tek kaynak' AS kontrol, count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM (SELECT gun, hesap_id, kampanya_id FROM raw.meta_harcama
         GROUP BY 1,2,3 HAVING count(DISTINCT kaynak) > 1) t
UNION ALL
SELECT 'tek para birimi', count(DISTINCT para_birimi)::text, '1',
       CASE WHEN count(DISTINCT para_birimi) <= 1 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.meta_harcama WHERE para_birimi IS NOT NULL;

\echo ''
\echo '=== H) VIEW''LAR ARASI TUTARLILIK ==='
-- 🔴 Bu bolum, projenin kok bulgusunun tekrarini onler: birbirinden turemis
--    iki sayi ayni seyi soylemek zorundadir. Kalem indirimi hatasi aylarca
--    gorunmedi cunku kimse iki rakami yan yana koymadi.
SELECT 'mart.gunluk cirosu = mart.gunluk_marj cirosu' AS kontrol,
       coalesce(a.c,0)::text || ' / ' || coalesce(b.c,0)::text AS deger,
       CASE WHEN coalesce(a.c,0) = coalesce(b.c,0) THEN 'SUCCESS' ELSE 'FAILED' END AS durum
  FROM (SELECT sum(ciro_dogrulanmis + ciro_beyan_edilmis) AS c FROM mart.gunluk) a,
       (SELECT sum(ciro) AS c FROM mart.gunluk_marj) b
UNION ALL
SELECT 'mart.gunluk kargosu = gunluk_marj kargo_tum',
       coalesce(a.k,0)::text || ' / ' || coalesce(b.k,0)::text,
       CASE WHEN coalesce(a.k,0) = coalesce(b.k,0) THEN 'SUCCESS' ELSE 'FAILED' END
  FROM (SELECT sum(kargo_maliyeti) AS k FROM mart.gunluk) a,
       (SELECT sum(kargo_tum) AS k FROM mart.gunluk_marj) b
UNION ALL
-- Siparis seviyesi ile kalem seviyesi ayni ciroyu vermeli.
SELECT 'siparis seviyesi = kalem seviyesi ciro',
       to_char(a.c,'FM999999990.00') || ' / ' || to_char(b.c,'FM999999990.00'),
       CASE WHEN round(a.c,2) = round(b.c,2) THEN 'SUCCESS' ELSE 'FAILED' END
  FROM (SELECT coalesce(sum(ciro_dogrulanmis),0)+coalesce(sum(ciro_beyan_edilmis),0) AS c
          FROM mart.siparis) a,
       (SELECT coalesce(sum(satir_ciro),0) AS c FROM mart.siparis_kalem
         WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')) b;

\echo ''
\echo '=== I) KONUSMA (CR-011) ==='
-- 🔴 Bu bolum ATIF sinamaz - atif kurulamiyor. Veri butunlugu sinar.
-- 🔴 "Mesajsiz konusma" TEK BASINA HATA DEGIL: Meta'da acilmis ama hic
--    mesaj yazilmamis sohbet olabilir (olculdu: konusma #8, mesaj_sayisi=0,
--    gercek=0 - tutarli). Ilk surum bunu UYARI sayiyordu ve YANLIS POZITIF
--    uretiyordu. Gercek eksiklik sudur: konusma "N mesajim var" diyor ama
--    mesaj tablosunda o kadar yok - yani cekim EKSIK kalmis.
SELECT 'mesaj sayisi tutuyor' AS kontrol, count(*)::text AS deger, '0' AS beklenen,
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'UYARI (eksik cekim)' END AS durum
  FROM lcarlie.konusma k
 WHERE k.mesaj_sayisi > 0
   AND (SELECT count(*) FROM lcarlie.mesaj m WHERE m.konusma_id=k.id) < k.mesaj_sayisi
UNION ALL
SELECT 'yetim mesaj yok (konusmasiz)', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM lcarlie.mesaj m
 WHERE NOT EXISTS (SELECT 1 FROM lcarlie.konusma k WHERE k.id=m.konusma_id)
UNION ALL
-- 🔴 PII mart'a SIZMAMALI: konusma view'lari yalniz takma kimlik tasir.
SELECT 'mart.konusma_cevapsiz''ta PII yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.konusma_cevapsiz
 WHERE musteri_takma !~ '^[0-9a-f]{8}$'
UNION ALL
-- 🔴 HICBIR KONUSMA `olcumde` FILTRESINDEN DUSMESIN.
--    Mesaji olmayan bos sohbetin gunu NULL'dur. Onceki surumde `olcumde`
--    de NULL donuyordu; panel `WHERE olcumde` yazdigi icin o satir NE
--    "olcumde" NE "olcum disi" sayiliyor, SESSIZCE kayboluyordu.
--    CR-008'de ciroda yasanan NULL tuzaginin aynisi.
--
-- 🔴 TESTIN DUYARLILIGI: toplami tek basina saymak BU HATAYI YAKALAMAZ -
--    satir view'da duruyor, yalnizca bayragi NULL. O yuzden test
--    "olcumde" ve "olcum disi" DALLARININ TOPLAMI kaynak sayimina esit mi
--    diye sorar; bayrak NULL ise iki dala da girmez ve toplam eksik cikar.
SELECT 'olcumde bayragi hic konusma dusurmuyor',
       (SELECT coalesce(sum(yeni_konusma) FILTER (WHERE olcumde),0)
             + coalesce(sum(yeni_konusma) FILTER (WHERE NOT olcumde),0)
          FROM mart.konusma_gunluk)::text,
       (SELECT count(*) FROM lcarlie.konusma)::text,
       CASE WHEN (SELECT coalesce(sum(yeni_konusma) FILTER (WHERE olcumde),0)
                       + coalesce(sum(yeni_konusma) FILTER (WHERE NOT olcumde),0)
                    FROM mart.konusma_gunluk)
               = (SELECT count(*) FROM lcarlie.konusma)
            THEN 'SUCCESS' ELSE 'FAILED' END;

\echo ''
\echo '=== J) TAZELIK ==='
-- 🔴 "Hic calismama" durumu: cron atlarsa yeni log satiri olmaz, alarm da olmaz.
--
-- 🔴 BEKLENEN KAYNAK LISTESI SABIT (ikinci tur denetimi).
--    Onceki hali `FROM raw.yukleme_log GROUP BY kaynak` idi: bir kaynak
--    HIC satir yazmamissa o kaynak icin satir uretilmez, dolayisiyla FAILED
--    de uretilmezdi. Yorum "hic calismama durumu" diyordu ama kod yalnizca
--    BAYAT satiri yakaliyordu, YOK OLAN kaynagi degil. Yani wix_urun ETL'i
--    tamamen silinse test yesil yanmaya devam ederdi.
SELECT b.kaynak,
       coalesce(to_char(max(l.bitis) AT TIME ZONE 'Europe/Istanbul','DD.MM HH24:MI'),'-') AS son,
       coalesce(round(extract(epoch FROM now()-max(l.bitis))/3600.0,1)::text,'-') AS saat_once,
       CASE WHEN max(l.bitis) IS NULL THEN 'FAILED (hic calismamis)'
            WHEN max(l.bitis) > now() - interval '30 hours' THEN 'SUCCESS'
            ELSE 'FAILED (hat durmus olabilir)' END AS durum
  FROM (VALUES ('wix'),('basitkargo'),('meta_reklam'),('wix_urun')) b(kaynak)
  LEFT JOIN raw.yukleme_log l ON l.kaynak = b.kaynak
 GROUP BY b.kaynak ORDER BY 1;

\echo ''
\echo '=== K) KDV VE PARA ZINCIRI (CR-012) ==='
-- 🔴 KDV 16.09.2026'da bulundu: 'toplam' KDV DAHILDIR ve marj bu sayidan
--    hesaplaniyordu. Marj 47.073,50 yerine 35.494,58 olmaliydi - %24,6 sisik.
--    Asagidaki testler ayni hatanin sessizce geri gelmesini engeller.

-- 1) Kalemlerin KDV HARIC toplami, siparişin KDV haric tutarina esit olmali.
--    🔴 Bu, A bolumundeki KDV DAHIL testinin esidir; ikisi BIRLIKTE durmali.
--       Yalniz biri olsaydi oransal dagitimda bir hata fark edilmezdi.
--
--    🔴🔴 SAG TARAF BILEREK `sum(toplam) - sum(kdv)`; `sum(toplam - kdv)` DEGIL.
--    Ilk yazdigim hali `sum(toplam - kdv)` idi ve DUYARLILIK SINAMASINDA
--    KALDI (16.09.2026): bir siparişin KDV'si silinince
--      - sol taraf o siparişin kalemlerini NULL yapip DUSURUYOR,
--      - sag taraf da ayni siparişi NULL yapip DUSURUYOR,
--    iki taraf ayni miktarda eksiliyor ve esitlik BOZULMUYORDU. Yani test
--    "tamam" derken bir siparişin tum cirosu hesaptan cikmis oluyordu.
--    Bu, denetimin uyardigi "ayni yanlis kaynaktan turemis iki sayi
--    birbirini dogrular" tuzaginin tam ornegi - ve bu kez BENIM testimde.
--    `sum(toplam) - sum(kdv)` NULL'da toplami korur, kdv'yi dusurur; iki
--    taraf ayrisir ve hata YAKALANIR. Sinandi: yakaliyor.
SELECT 'kalem KDV haric toplami = siparis KDV haric' AS kontrol,
       to_char(k.net,'FM999999990.00') AS kalem,
       to_char(s.net,'FM999999990.00') AS siparis,
       CASE WHEN round(k.net,2) = round(s.net,2) THEN 'SUCCESS'
            ELSE 'FAILED (fark: ' || to_char(k.net-s.net,'FM999999990.00') || ')' END AS durum
  FROM (SELECT sum(satir_ciro_net)          AS net FROM mart.siparis_kalem) k,
       (SELECT sum(toplam) - sum(kdv)       AS net FROM raw.wix_order)      s;

-- 2) KDV hic bir sipariste tutardan BUYUK olamaz, negatif olamaz.
SELECT 'KDV tutari makul aralikta', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM raw.wix_order
 WHERE kdv IS NOT NULL AND (kdv < 0 OR kdv >= toplam);

-- 3) Sayilan (ciro uretilen) her siparişte KDV okunabilmis olmali.
--    🔴 Okunamazsa net ciro NULL olur ve marj SESSIZCE kaybolur - tam da
--       projenin defalarca yasadigi "para buharlasmasi" deseni.
SELECT 'sayilan siparişte KDV eksik yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis
 WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS') AND kdv IS NULL;

-- 4) Para zinciri sirasi: teslim edilen bir siparis kargolanmis OLMALI.
--    🔴 Tersi mumkun (kargolandi ama henuz teslim degil); bu yon imkansizdir.
SELECT 'teslim edilen mutlaka kargolanmis', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis_para
 WHERE teslim_edildi AND NOT kargolandi;

-- 5) Tahsil edilmis kapida odeme, teslim edilmemis olamaz.
--    🔴 Para kuryeden geliyor; teslimat olmadan tahsilat olamaz.
SELECT 'COD tahsilati teslimatsiz degil', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis_para
 WHERE cod_tahsil_edilen > 0 AND teslim_edildi IS DISTINCT FROM true;

-- 6) Hazirlik kapisinin hicbir kosulu NULL donmemeli.
--    🔴 NULL bir kosul ne "saglandi" ne "saglanmadi" sayilir; bool_and()
--       NULL uretir ve panel "hazir mi bilinmiyor" haline duser.
--       Bu, CR-008/CR-011'de iki kez yasanan NULL tuzaginin ucuncu yeri.
SELECT 'hazirlik kosullarinda NULL yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.hazirlik WHERE saglandi IS NULL;

-- 7) Gunluk anlik goruntu zinciri kopmamis olmali.
--    🔴 Yazilmazsa "o gun ekranda ne yaziyordu" sorusu cevapsiz kalir ve
--       bu geriye donuk telafi EDILEMEZ - view'lar bugunku mantigi uygular.
--
--    🔴 25.09.2026 DUZELTMESI - SIRALAMA HATASI. Eski hali YALNIZ BUGUNUN
--    kaydini ariyordu. Ama bu sorguyu calistiran ticari-kontrol.sh, gunun
--    anlik goruntusunu ~100 satir SONRA yaziyor (mutabakat 298. satir,
--    core.anlik_yaz() 411. satir). Yani kontrol her gun, kendi betigi o
--    kaydi yazmadan once "yok" diyordu.
--    Olculdu: 22, 23 ve 24 Eylul'de ucu de UYARI verdi ve ucunde de
--    e-posta gonderildi -- oysa zincirde HIC kopukluk yoktu (34 kayit,
--    son 7 gunde 13). Her gun gelen ve her gun yanlis olan bir alarm,
--    gercek alarmi gorunmez kilar.
--
--    Asil sinanmak istenen sey "bugun saat 08:30 itibariyle yazildi mi"
--    degil, ZINCIR KOPMADI MI. Bugunun ya da dunun kaydi varsa zincir
--    saglamdir; ikisi birden yoksa gercekten bir gun kaybedilmistir ve
--    bu bir UYARI degil FAILED'dir.
SELECT 'gunluk anlik goruntu zinciri saglam',
       (SELECT count(*)::text FROM core.rapor_anlik
         WHERE rapor_gunu >= (now() AT TIME ZONE 'Europe/Istanbul')::date - 1),
       '>=1',
       CASE WHEN EXISTS (SELECT 1 FROM core.rapor_anlik
                          WHERE rapor_gunu >= (now() AT TIME ZONE 'Europe/Istanbul')::date - 1)
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- =============================================================================
-- COGS / UNIT ECONOMICS  (17.09.2026)
-- 🔴 Bu katmanin en buyuk riski SESSIZ IYIMSERLIK: bilinmeyen bir maliyetin
--    sifir sayilmasi. Asagidaki kontroller tam olarak onu kovalar.
-- =============================================================================

-- 8) Ekonomi cirosu, siparis aynasiyla MUTABIK olmali.
--    🔴 gelir_durumu kirilimi ciroyu BOLER; bolunmus parcalarin toplami
--       butune esit degilse bir siparis iki kez ya da hic sayilmis demektir.
SELECT 'ekonomi cirosu siparis aynasiyla mutabik',
       (SELECT round(sum(net_ciro_kdv_haric),2)::text FROM mart.siparis_ekonomi),
       (SELECT round(sum(toplam - kdv),2)::text FROM raw.wix_order),
       CASE WHEN (SELECT round(sum(net_ciro_kdv_haric),2) FROM mart.siparis_ekonomi)
                 IS NOT DISTINCT FROM
                 (SELECT round(sum(toplam - kdv),2) FROM raw.wix_order)
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 9) INCOMPLETE bir siparis ASLA ekonomik olarak dogrulanmis sayilamaz.
--    🔴 Bu, "UNKNOWN = 0" hatasinin en dogrudan tespiti. Bir gun biri
--       coalesce(...,0) eklerse bu satir kirmizi yanar.
SELECT 'INCOMPLETE siparis ekonomik dogrulanmis DEGIL', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis_ekonomi
 WHERE tamlik = 'INCOMPLETE' AND ekonomik_dogrulanmis;

-- 10) Eksik bileseni olan siparis COMPLETE olamaz.
--     🔴 Tamlik etiketi ile eksik listesi AYNI GERCEGI soylemeli; ayrisirlarsa
--        panel "tam" der, liste "eksik" der ve okuyan ilkine inanir.
SELECT 'eksik bileseni olan siparis COMPLETE degil', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis_ekonomi
 WHERE cardinality(eksik_bilesenler) > 0 AND tamlik = 'COMPLETE';

-- 11) Siparise yazilan kargo, bagli gonderilerin maliyetiyle BIREBIR esit.
--     🔴 CIFT SAYIM KORUMASI: extraFee zaten shipmentFee'nin icinde; biri
--        ayrica eklerse bu satir tutmaz. Ayrica ortalama kargo dagitimi
--        yapilirsa da tutmaz - ki yapilmamali.
--     🔴 KARSILASTIRMA HAM VERIYE KARSI YAPILIR, mart.gonderi'ye DEGIL.
--        Ilk surumde iki taraf da mart.gonderi'den okunuyordu; bu TOTOLOJIYDI
--        (17.09.2026'da duyarlilik sinamasinda bulundu: bir gonderinin
--        maliyeti 999.999 yapildiginda IKI TARAF DA birlikte degisti ve
--        kontrol hic kizarmadi). Bagimsiz taraf raw.bk_shipment'tir.
SELECT 'siparis kargosu ham veriyle esit',
       (SELECT round(coalesce(sum(kargo_maliyet),0),2)::text FROM mart.siparis_ekonomi),
       (SELECT round(coalesce(sum((ham#>>'{priceInfo,totalCost}')::numeric),0),2)::text
          FROM raw.bk_shipment b
         WHERE b.foreign_code IN (SELECT siparis_id FROM raw.wix_order)),
       CASE WHEN (SELECT round(coalesce(sum(kargo_maliyet),0),2) FROM mart.siparis_ekonomi)
                 = (SELECT round(coalesce(sum((ham#>>'{priceInfo,totalCost}')::numeric),0),2)
                      FROM raw.bk_shipment b
                     WHERE b.foreign_code IN (SELECT siparis_id FROM raw.wix_order))
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 12) COD komisyonu yalniz OLCULMUS olanlardan toplanir.
--     🔴 NOT_YET_KNOWN (tahsilat bekleyen) bir komisyon 0 TL SAYILMAZ;
--        toplama girerse bekleyen maliyet sessizce yok olur.
--     🔴 Bu da HAM VERIYE karsi olculur (ayni totoloji tuzagi).
--        Ham taraf: tahsilati GERCEKLESMIS (TRANSFERRED) gonderilerin fee'si.
--        Bekleyen tahsilatin fee'si NULL'dur ve toplama GIRMEMELIDIR.
SELECT 'COD komisyonu yalniz gerceklesmis tahsilattan',
       (SELECT round(coalesce(sum(cod_komisyon),0),2)::text FROM mart.siparis_ekonomi),
       (SELECT round(coalesce(sum((ham#>>'{codInfo,fee}')::numeric),0),2)::text
          FROM raw.bk_shipment b
         WHERE b.foreign_code IN (SELECT siparis_id FROM raw.wix_order)
           AND b.ham#>>'{codInfo,collectionStatus}' = 'TRANSFERRED'),
       CASE WHEN (SELECT round(coalesce(sum(cod_komisyon),0),2) FROM mart.siparis_ekonomi)
                 = (SELECT round(coalesce(sum((ham#>>'{codInfo,fee}')::numeric),0),2)
                      FROM raw.bk_shipment b
                     WHERE b.foreign_code IN (SELECT siparis_id FROM raw.wix_order)
                       AND b.ham#>>'{codInfo,collectionStatus}' = 'TRANSFERRED')
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 13) Siparis grain'inde REKLAM MALIYETI KOLONU BULUNMAMALI.
--     🔴 Yapisal koruma: order-level deterministik atif kurulamadi (CR-011,
--        ad eslesmesi 0/259). Boyle bir kolon acilirsa bir gun birisi
--        doldurur ve "bu siparisin reklam maliyeti" uydurulmus olur.
SELECT 'siparis grain''inde reklam maliyeti kolonu YOK', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM information_schema.columns
 WHERE table_schema='mart' AND table_name='siparis_ekonomi'
   AND (column_name ILIKE '%reklam%' OR column_name ILIKE '%harcama%'
        OR column_name ILIKE '%media%' OR column_name ILIKE '%roas%');
-- 14) UST SINIR, bilinen katkidan KUCUK OLAMAZ.
--     🔴 Cozulmemis bilesenlerin tamami maliyettir (>= 0) ve katkiyi yalniz
--        DUSURUR; tek yukari yonlu bilesen COGS KDV tabanidir ve ust sinira
--        dahildir. Dolayisiyla ust_sinir >= bilinen_katki HER ZAMAN dogrudur.
--        Tersi cikarsa sinir matematigi bozulmus demektir.
SELECT 'katki ust siniri bilinen katkidan kucuk degil', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis_ekonomi
 WHERE en_iyi_olasi_katki < bilinen_bilesen_katkisi;

-- 15) NEGATIVE_PROVEN_BY_BOUND, ECONOMICALLY_VALIDATED ile KARISTIRILAMAZ.
--     🔴 Yon kanitli olabilir ama tutar bilinmiyor olabilir. Ikisi ayni anda
--        dogru olmak ZORUNDA DEGIL; ama "yon negatif kanitli" iken sistem
--        scale ONERMEMELI.
SELECT 'negatif yon kanitliyken scale KAPALI', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.ticari_yasayabilirlik
 WHERE ticari_yon = 'NEGATIVE_PROVEN_BY_BOUND' AND scale_konusulabilir;

-- 16) Tamlik BILESEN BAZLI olmali - parasal esik KULLANILMAMALI.
--     🔴 Locked design: keyfi materiality threshold YOK. core.ayar icinde
--        boyle bir esik belirirse bu kontrol uyarir.
SELECT 'parasal materiality esigi YOK', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.ayar
 WHERE anahtar ILIKE '%materyal%' OR anahtar ILIKE '%materiality%';

-- 17) KRITIK bilesen eksikken ekonomi COMPLETE olamaz.
SELECT 'kritik eksik varken COMPLETE yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.siparis_ekonomi
 WHERE cardinality(kritik_eksik) > 0 AND tamlik = 'COMPLETE';
-- =============================================================================
-- KALICI REGRESYON KURALI: yeni cozulmemis bilesen sinir kanitini
-- SESSIZCE gecersiz kilamaz.  (17.09.2026, Chief Architect frozen baseline)
-- =============================================================================

-- 18) Her ACIK bilesenin KATKI YONU beyan edilmis olmali.
--     🔴 Yon beyan edilmeden bir bilesen katki/sinir hesabina giremez.
--        Varsayilan 'BILINMIYOR' oldugu icin, beyan edilmeden eklenen her
--        yeni satir burada KIRMIZI yanar - sessizce gecemez.
SELECT 'her acik bilesenin katki yonu beyan edilmis', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.maliyet_bileseni
 WHERE gecerli_bitis IS NULL AND katki_yonu = 'BILINMIYOR';

-- 19) Katkiyi ARTIRABILEN cozulmemis bir bilesen UST SINIRA DAHIL OLMALI.
--     🔴 mart.siparis_ekonomi.en_iyi_olasi_katki bugun YALNIZ COGS KDV
--        tabanini ust sinira ekler (o da core.ayar'da tutulur, bu tabloda
--        DEGIL). Bu tabloda katki_yonu='ARTIRIR' olan ve degeri cozulmemis
--        bir satir belirirse ust sinir OLDUGUNDAN DUSUK kalir ve
--        NEGATIVE_PROVEN_BY_BOUND kaniti GECERSIZLESIR.
--        Boyle bir satir eklendiginde once view guncellenmeli.
SELECT 'ARTIRIR yonlu cozulmemis bilesen ust sinira dahil', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.maliyet_bileseni
 WHERE gecerli_bitis IS NULL AND katki_yonu = 'ARTIRIR' AND deger IS NULL;

-- 20) Her ACIK bilesen mart.siparis_ekonomi tarafindan ISLENIYOR olmali.
--     🔴 SESSIZ IHMAL KORUMASI. View bilesenleri ADIYLA okuyor
--        (PAKETLEME · ODEME_KOMISYONU · KANAL_KOMISYONU). Tabloya dorduncu
--        bir satir eklenirse view onu HIC GORMEZ: ne katkiya girer, ne
--        eksik_bilesenler listesinde cikar. Yani maliyet sessizce
--        KAYBOLUR ve katki oldugundan yuksek gorunur.
--        Bu kontrol, yeni bilesen ekleyenin view'i de guncellemesini ZORUNLU kilar.
--        🔴 Liste elle tutuluyor: view degistiginde BURASI da degismeli.
SELECT 'acik bilesenlerin tamami ekonomi view''inde isleniyor',
       (SELECT count(*)::text FROM core.maliyet_bileseni
         WHERE gecerli_bitis IS NULL
           AND bilesen NOT IN ('PAKETLEME','ODEME_KOMISYONU','KANAL_KOMISYONU')),
       '0',
       CASE WHEN (SELECT count(*) FROM core.maliyet_bileseni
                   WHERE gecerli_bitis IS NULL
                     AND bilesen NOT IN ('PAKETLEME','ODEME_KOMISYONU','KANAL_KOMISYONU')) = 0
            THEN 'SUCCESS' ELSE 'FAILED' END;
-- =============================================================================
-- CR-017  GA4 / FUNNEL TRUTH  (17.09.2026)
-- 🔴 Bu katmanin en buyuk riski: "olculmedi" ile "gerceklesmedi"nin
--    karismasi. Asagidaki kontroller tam olarak onu kovalar.
-- =============================================================================

-- 21) behavior semantigi: veri yokken PARTIAL DENMEZ.
--     🔴 PARTIAL = "kismen VERI mevcut". Ambarda sifir satir varken PARTIAL
--        yazmak, okuyana "kismen davranis verimiz var" dedirtir.
SELECT 'davranis verisi yokken behavior PARTIAL degil', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.source_authority
 WHERE alan='behavior' AND current_connection='PARTIAL'
   AND NOT EXISTS (SELECT 1 FROM raw.ga4_event);

-- 22) NOT_MEASURED asla 0 gibi raporlanmaz: gozlenmeyense sayi URETILMEZ.
SELECT 'NOT_MEASURED adimda oran URETILMEMIS', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.funnel_orani WHERE oran_durumu <> 'HESAPLANDI' AND oran_yuzde IS NOT NULL;

-- 23) Enstrumantasyonu olmayan adim ASLA OBSERVED olamaz.
SELECT 'enstrumantasyonsuz adim OBSERVED degil', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.funnel_saglik
 WHERE enstrumantasyon IN ('NOT_INSTRUMENTED','NOT_TESTED') AND gozlem_durumu='OBSERVED';

-- 24) GA4 TICARI OTORITE DEGILDIR: ciro view'lari raw.ga4_event okumamali.
--     🔴 YAPISAL KORUMA. Bir gun biri GA4 purchase value'sunu ciroya
--        karistirirsa bu satir kizarir.
SELECT 'ciro view''lari GA4 okumuyor', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM information_schema.view_table_usage
 WHERE view_schema='mart'
   AND view_name IN ('siparis','siparis_kalem','siparis_ekonomi','ekonomi_gunluk',
                     'nakit_gunluk','ticari_yasayabilirlik')
   AND table_name = 'ga4_event';

-- 25) purchase duplicate korumasi: ayni transaction_id iki kez SAYILAMAZ.
SELECT 'GA4 purchase duplicate yok', 
       (SELECT coalesce(duplicate_islem,0)::text FROM mart.ga4_siparis_mutabakat), '0',
       CASE WHEN (SELECT coalesce(duplicate_islem,0) FROM mart.ga4_siparis_mutabakat)=0
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 26) Wix siparis sayisi GA4'ten BAGIMSIZ kalmali.
--     🔴 GA4 hic veri gondermese bile ticari siparis sayisi DEGISMEZ.
SELECT 'Wix siparis sayisi GA4''ten bagimsiz',
       (SELECT wix_siparis_sayisi::text FROM mart.ga4_siparis_mutabakat),
       (SELECT count(*)::text FROM mart.siparis),
       CASE WHEN (SELECT wix_siparis_sayisi FROM mart.ga4_siparis_mutabakat)
                 = (SELECT count(*) FROM mart.siparis)
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 27) Funnel adimlarinin tamami OLCUM KANITI tasimali.
--     🔴 Kanitsiz bir kapsama beyani, beyandir - olcum degil.
SELECT 'her funnel adimi olcum kaniti tasiyor', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.funnel_adim WHERE btrim(coalesce(olcum_kaniti,'')) = '';

-- 28) ROAS kapisi CR-017 ile DEGISMEMELI.
--     🔴 GA4 kurulmasi tek basina ROAS gate'i ACMAZ.
SELECT 'ROAS kapisi CR-017 ile degismedi',
       (SELECT karar FROM mart.roas_kapisi), 'ROAS_KARAR_METRIGI_OLAMAZ',
       CASE WHEN (SELECT karar FROM mart.roas_kapisi)='ROAS_KARAR_METRIGI_OLAMAZ'
            THEN 'SUCCESS' ELSE 'FAILED' END;
-- =============================================================================
-- CR-017 KAPSAM DUZELTMESI: URUN BAGIMSIZLIK  (17.09.2026)
-- 🔴 Vireon yalnizca ILK KANIT ORNEGIDIR. Sistem L'CARLIE GENELI icindir.
--    Asagidaki kontroller mimarinin bir urune GOMULMESINI engeller.
-- =============================================================================

-- 29) IS MANTIGI VIEW'LARINDA URUN LITERALI OLMAMALI.
--     🔴 Bir urun adi/sayfasi view govdesine yazilirsa yeni urun eklendiginde
--        sessizce KAPSAM DISI kalir. Kanit/fixture satirlari tabloda durabilir;
--        VIEW TANIMINDA duramaz.
SELECT 'is mantigi view''larinda urun literali yok', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM pg_views
 WHERE schemaname='mart'
   AND viewname IN ('fiyat_gercegi','funnel_kapsama_matrisi','davranis_kapsama_matrisi',
                    'funnel_saglik','funnel_orani','siparis_ekonomi','ekonomi_gunluk')
   AND (definition ILIKE '%vireon%' OR definition ILIKE '%femisia%'
        OR definition ILIKE '%intimblanc%' OR definition ILIKE '%hydravie%'
        OR definition ILIKE '%dermavasc%' OR definition ILIKE '%dermamovera%');

-- 30) HER URUNUN fiyat gercegi SATIRI olmali (degeri bilinmese de).
--     🔴 Satiri olmayan urun, fiyat sorusunda SESSIZCE yok sayilirdi.
SELECT 'her urunun fiyat gercegi satiri var',
       (SELECT count(*)::text FROM raw.wix_urun u
         WHERE NOT EXISTS (SELECT 1 FROM core.urun_fiyat_gercegi f WHERE f.urun_id=u.urun_id)),
       '0',
       CASE WHEN (SELECT count(*) FROM raw.wix_urun u
                   WHERE NOT EXISTS (SELECT 1 FROM core.urun_fiyat_gercegi f WHERE f.urun_id=u.urun_id))=0
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 31) HER NATIVE URUN SAYFASI registry'de olmali.
--     🔴 Yeni urun eklendiginde sayfa registry'si buyumezse funnel kapsamasi
--        o urunu HIC gormez.
SELECT 'her native urun sayfasi kayitli',
       (SELECT count(*)::text FROM raw.wix_urun u
         WHERE u.ham#>>'{productPageUrl,path}' IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM core.sayfa_urun s
                            WHERE s.sayfa_yolu = u.ham#>>'{productPageUrl,path}')),
       '0',
       CASE WHEN (SELECT count(*) FROM raw.wix_urun u
                   WHERE u.ham#>>'{productPageUrl,path}' IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM core.sayfa_urun s
                                      WHERE s.sayfa_yolu = u.ham#>>'{productPageUrl,path}'))=0
            THEN 'SUCCESS' ELSE 'FAILED' END;

-- 32) OLCULMEMIS SAYFA "calisiyor" SAYILMAMALI.
--     🔴 Kapsama matrisinde olculmemis her satir NOT_TESTED olmali; bos
--        birakilsaydi okuyan "sorun yok" diye anlardi.
SELECT 'olculmemis sayfa NOT_TESTED', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM mart.funnel_kapsama_matrisi
 WHERE NOT olculdu AND enstrumantasyon <> 'NOT_TESTED';

-- 33) SAYFA-URUN BAGI DETERMINISTIK olmali (urun ADI ile eslestirme YOK).
--     🔴 Registry'deki her urun_id gercek katalogda bulunmali; ad benzerligiyle
--        kurulmus bir bag OLMAMALI.
SELECT 'sayfa-urun bagi katalogda dogrulaniyor', count(*)::text, '0',
       CASE WHEN count(*)=0 THEN 'SUCCESS' ELSE 'FAILED' END
  FROM core.sayfa_urun s
 WHERE s.urun_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM raw.wix_urun u WHERE u.urun_id = s.urun_id);