\pset format unaligned
\pset fieldsep ' | '
\t on

\echo '=== 1) EN GUCLU KURALLAR (soru >=5 kez sorulmus, baskin cevap) ==='
SELECT lpad(k.adet::text,3) || 'x  %' || lpad(k.oran::text,6) || '  "' || left(k.ornek_soru,34) || '"'
       || E'\n        -> ' || left(regexp_replace(k.ornek_cevap, E'[\n\r]+', ' ', 'g'), 110)
FROM lcarlie.kalip k
WHERE k.adet >= 5
ORDER BY k.adet DESC LIMIT 12;

\echo ''
\echo '=== 2) KARARSIZ SORULAR (ayni soruya farkli cevaplar) ==='
SELECT '"' || left(min(ornek_soru),30) || '"  ' || count(*) || ' farkli cevap, toplam ' || sum(adet) || ' kez'
FROM lcarlie.kalip GROUP BY soru_norm HAVING count(*) > 2 AND sum(adet) >= 6
ORDER BY sum(adet) DESC LIMIT 8;

\echo ''
\echo '=== 3) CEVAP SABLONLARININ KAPSAMI ==='
SELECT lpad(sum(adet)::text,4) || 'x  ' || count(DISTINCT soru_norm) || ' farkli soruya  "' || left(cevap_imza,58) || '"'
FROM lcarlie.kalip GROUP BY cevap_imza ORDER BY sum(adet) DESC LIMIT 8;

\echo ''
\echo '=== 4) CEVAP GECIKMESI (medyan saniye) ==='
SELECT CASE WHEN gecikme_sn < 60 THEN 'anlik (<1dk)'
            WHEN gecikme_sn < 3600 THEN '1dk-1saat'
            WHEN gecikme_sn < 86400 THEN '1-24 saat'
            ELSE '1 gunden fazla' END AS dilim, sum(adet) AS n
FROM lcarlie.kalip GROUP BY 1 ORDER BY n DESC;

\echo ''
\echo '=== 5) OZET ==='
SELECT 'kalip=' || count(*) || ' | eslesen soru-cevap cifti=' || sum(adet)
     || ' | tekil soru=' || count(DISTINCT soru_norm)
     || ' | tekil cevap sablonu=' || count(DISTINCT cevap_imza)
FROM lcarlie.kalip;
