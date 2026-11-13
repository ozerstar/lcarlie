-- Overture eczane kayıtlarını il'e ve core.eczane_hedef'e bağlar (13.11.2026).
-- Overture'da `region` ya boş (10.609'un 8.324'ü) ya plaka kodu ('06').
-- Sıra: plaka -> telefon (ülke geneli, tekil) -> adreste il adı -> tekil ad.
BEGIN;

CREATE TEMP TABLE plaka (kod text PRIMARY KEY, il text);
INSERT INTO plaka VALUES
('01','Adana'),('02','Adıyaman'),('03','Afyonkarahisar'),('04','Ağrı'),('05','Amasya'),
('06','Ankara'),('07','Antalya'),('08','Artvin'),('09','Aydın'),('10','Balıkesir'),
('11','Bilecik'),('12','Bingöl'),('13','Bitlis'),('14','Bolu'),('15','Burdur'),('16','Bursa'),
('17','Çanakkale'),('18','Çankırı'),('19','Çorum'),('20','Denizli'),('21','Diyarbakır'),
('22','Edirne'),('23','Elazığ'),('24','Erzincan'),('25','Erzurum'),('26','Eskişehir'),
('27','Gaziantep'),('28','Giresun'),('29','Gümüşhane'),('30','Hakkari'),('31','Hatay'),
('32','Isparta'),('33','Mersin'),('34','İstanbul'),('35','İzmir'),('36','Kars'),
('37','Kastamonu'),('38','Kayseri'),('39','Kırklareli'),('40','Kırşehir'),('41','Kocaeli'),
('42','Konya'),('43','Kütahya'),('44','Malatya'),('45','Manisa'),('46','Kahramanmaraş'),
('47','Mardin'),('48','Muğla'),('49','Muş'),('50','Nevşehir'),('51','Niğde'),('52','Ordu'),
('53','Rize'),('54','Sakarya'),('55','Samsun'),('56','Siirt'),('57','Sinop'),('58','Sivas'),
('59','Tekirdağ'),('60','Tokat'),('61','Trabzon'),('62','Tunceli'),('63','Şanlıurfa'),
('64','Uşak'),('65','Van'),('66','Yozgat'),('67','Zonguldak'),('68','Aksaray'),
('69','Bayburt'),('70','Karaman'),('71','Kırıkkale'),('72','Batman'),('73','Şırnak'),
('74','Bartın'),('75','Ardahan'),('76','Iğdır'),('77','Yalova'),('78','Karabük'),
('79','Kilis'),('80','Osmaniye'),('81','Düzce');

-- İl ipuçları (alan kodu, OSM ilçe->il) migrations/eczane-il-ipucu.sql ile
-- bu dosyadan ÖNCE uygulanır; il boş kalan kayıt eşleşmeye giremez.

-- 1) Plaka kodu -> il adı
UPDATE raw.eczane_kaynak k SET il = p.il FROM plaka p
WHERE k.kaynak = 'OVERTURE' AND k.il = p.kod;

-- 2) Telefonla: numara hedef listesinde TEK eczanede geçiyorsa (ülke geneli)
WITH ht AS (
  SELECT right(regexp_replace(telefon,'\D','','g'),10) t, min(id) id, min(il) il
  FROM core.eczane_hedef WHERE telefon IS NOT NULL AND durum <> 'GECERSIZ'
  GROUP BY 1 HAVING count(*) = 1)
UPDATE raw.eczane_kaynak k SET hedef_id = ht.id, eslesme = 'TELEFON', il = coalesce(k.il, ht.il)
FROM ht WHERE k.kaynak = 'OVERTURE' AND k.hedef_id IS NULL AND ht.t = ANY (k.telefonlar);

-- 3) İl hâlâ boşsa adreste geçen il adı ("… 06420 Çankaya/Ankara" ya da "…, Ankara")
UPDATE raw.eczane_kaynak k SET il = p.il FROM plaka p
WHERE k.kaynak = 'OVERTURE' AND k.il IS NULL
  AND k.adres ~* ('(/|,\s*|\s)' || p.il || '(\s*,|\s*$|\s+\d)');

CREATE OR REPLACE FUNCTION pg_temp.nrm(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT regexp_replace(translate(lower(replace(replace(coalesce(t,''),'İ','i'),'I','ı')),
         'çğıöşüâî','cgiosuai'), '(eczanesi|eczane|pharmacy|ecz\.?|\s|[^a-z0-9])', '', 'g') $$;

-- 4) Adla (il içinde iki tarafta da tekil ad)
WITH hk AS (SELECT id, il, pg_temp.nrm(eczane) n FROM core.eczane_hedef WHERE durum <> 'GECERSIZ'),
     hs AS (SELECT il, n FROM hk GROUP BY 1,2 HAVING count(*) = 1),
     kk AS (SELECT id, il, pg_temp.nrm(ad) n FROM raw.eczane_kaynak
            WHERE kaynak = 'OVERTURE' AND il IS NOT NULL),
     ks AS (SELECT il, n FROM kk GROUP BY 1,2 HAVING count(*) = 1)
UPDATE raw.eczane_kaynak k SET hedef_id = hk.id, eslesme = 'AD'
FROM kk JOIN ks USING (il, n) JOIN hs USING (il, n) JOIN hk USING (il, n)
WHERE k.id = kk.id AND k.hedef_id IS NULL AND length(kk.n) >= 3;

-- 5) Eşleşmeyen ama ili bilinen: yeni hedef. Adı eczane olmayan (ör. "Renn Pharma"
--    gibi belirsiz) kayıtlar da Overture'da birincil kategori pharmacy olduğu için alınır.
WITH yeni AS (
  INSERT INTO core.eczane_hedef (il, eczane, telefon, adres, ilce, kaynak, oncelik)
  SELECT DISTINCT ON (k.il, k.ad, k.telefonlar[1])
         k.il, k.ad, k.telefonlar[1], k.adres, k.ilce, 'OVERTURE',
         (SELECT min(oncelik) FROM core.eczane_hedef h WHERE h.il = k.il)
  FROM raw.eczane_kaynak k
  WHERE k.kaynak = 'OVERTURE' AND k.hedef_id IS NULL AND k.il IS NOT NULL
    -- Birincil kategori pharmacy olsa da "Kardeş Optik" gibi sızıntılar var (77 kayıt)
    AND pg_temp.nrm(k.ad) || lower(k.ad) ~ '(ecz|pharm|apotek)'
  ON CONFLICT (il, eczane, telefon) DO NOTHING
  RETURNING id, il, eczane, telefon)
UPDATE raw.eczane_kaynak k SET hedef_id = yeni.id, eslesme = 'YENI'
FROM yeni WHERE k.kaynak = 'OVERTURE' AND k.hedef_id IS NULL AND k.il = yeni.il
  AND k.ad = yeni.eczane AND k.telefonlar[1] IS NOT DISTINCT FROM yeni.telefon;

-- Eksik telefon/ilçe tamamlanır (var olan beyan EZİLMEZ)
UPDATE core.eczane_hedef h SET telefon = coalesce(h.telefon, k.telefonlar[1]),
       ilce = coalesce(h.ilce, k.ilce), guncellendi = now()
FROM raw.eczane_kaynak k WHERE k.hedef_id = h.id AND k.kaynak = 'OVERTURE'
  AND (h.telefon IS NULL OR h.ilce IS NULL);

-- E-postalar (rehber/marka alanları hariç)
INSERT INTO core.eczane_eposta (hedef_id, eposta, kaynak)
SELECT k.hedef_id, lower(trim(e)), 'OVERTURE'
FROM raw.eczane_kaynak k, unnest(k.epostalar) e
WHERE k.kaynak = 'OVERTURE' AND k.hedef_id IS NOT NULL
  AND lower(e) ~ '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
  AND split_part(lower(e),'@',2) NOT IN ('eczane.com.tr','eczaneleri.org','nobetcieczaneler.org',
      'firmasec.com','aeo.org.tr','teb.org.tr','ikas.com','tr.naos.com','bioderma.com.tr')
ON CONFLICT (hedef_id, eposta) DO NOTHING;

-- SAHA'dan gelen eski tek-sütun e-postalar da aynı tabloya
INSERT INTO core.eczane_eposta (hedef_id, eposta, kaynak, dogrulama, dogrulandi)
SELECT id, lower(eposta), coalesce(eposta_kaynak, 'SAHA'), eposta_dogrulama,
       CASE WHEN eposta_dogrulama IS NOT NULL THEN guncellendi END
FROM core.eczane_hedef WHERE eposta <> ''
ON CONFLICT (hedef_id, eposta) DO NOTHING;

SELECT eslesme, count(*) FROM raw.eczane_kaynak WHERE kaynak = 'OVERTURE' GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) eposta_satiri, count(DISTINCT hedef_id) epostali_eczane,
       count(DISTINCT h.il) il
FROM core.eczane_eposta e JOIN core.eczane_hedef h ON h.id = e.hedef_id;
COMMIT;
