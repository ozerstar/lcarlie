-- SAHA ŞEMA 4: Türkçe anahtar, ilçe normalizasyonu, hedef dışı eleme
--
-- ÜÇ ÖLÇÜLMÜŞ KUSUR:
--
-- 1) İLÇE LİSTESİ KULLANILAMAZ HALDE. Aynı ilçe dört ayrı seçenek olarak
--    çıkıyordu: 'Çankaya' 7.955, 'ÇANKAYA' 1, 'çankaya' 2, 'Cankaya' 2.
--    Ayrıca liste ilçe olmayan değerlerle doluydu: 'Ankara' (il, 568
--    kayıt), 'Batıkent'/'Çayyolu'/'Ümitköy' (semt), 'İç Anadolu Bölgesi'
--    (bölge) ve hatta 'Milas'/'Nilüfer'/'Şehitkamil' (başka illerin
--    ilçeleri -- kaynak verideki hata).
--
-- 2) OTOMOTİV KAYITLARI HEDEF LİSTESİNDE. 'Imza Oto Kuaför' berber
--    sanılmış, 'Iskitler Oto Sanayi Sitesi' otel sanılmıştı. Kaynak
--    (Overture) yanlış sınıflamış; bizim eşlememiz doğru çalışıyor.
--
--    🔴 KÖR BİR 'oto' FİLTRESİ YAZILAMAZ: veride 'Prof Dr M Ali Oto' diye
--    gerçek bir hekim var. Soyadı Oto. Bu yüzden kalıplar TEK KELİME
--    DEĞİL, kelime sınırlı ÖBEKlerdir ('oto kuaför', 'oto sanayi').
--    Aynı tuzağın bir başka yüzü: 'lastik' kalıbı sınırsız yazılırsa
--    'Plastik Cerrahi' eşleşir -- bu hatayı ölçüm sorgumda bizzat yaptım.
--
-- 3) FİLTRE SORGUSU 1,78 SANİYE. Panel her kutu işaretlenişinde facet
--    sayılarını yeniden hesaplıyor; görünüm ise 21 bin satırlık üç yönlü
--    UNION + DISTINCT ON'u her seferinde baştan kuruyordu. Kaynak veri
--    AYDA BİR değişiyor, ziyaret ise gün içinde. Bu yüzden ikisi ayrıldı:
--    kaynak MADDİLEŞTİRİLDİ, ziyaret canlı bağlanıyor.
--
-- HİÇBİR KAYIT SİLİNMEZ. Elenen kayıt `hedef_disi` işaretlenir ve NEDENİ
-- yazılır; ilçesi çözülemeyen kaydın ham değeri `ilce_ham`da durur.
-- Silseydik, yanlış elediğimizi bir daha göremezdik.

BEGIN;

-- 1) TÜRKÇE ARAMA ANAHTARI --------------------------------------------------
-- 'dis' yazan 'Diş'i bulsun. ILIKE büyük/küçük harfi zaten doğru çeviriyor
-- (ölçüldü: 'diş' ve 'DİŞ' ikisi de 560), ama aksanı çevirmiyor: Türkçe
-- karakteri olmayan klavyeden arayan kişi hiçbir şey bulamıyordu.
CREATE OR REPLACE FUNCTION core.tr_anahtar(m text) RETURNS text AS $$
  SELECT nullif(btrim(regexp_replace(
           lower(translate(coalesce(m, ''),
                 'ÇĞİIÖŞÜÂÎÛçğıiöşüâîû',
                 'cgiiosuaiucgiiosuaiu')),
           '[^a-z0-9]+', ' ', 'g')), '');
$$ LANGUAGE sql IMMUTABLE;

-- 2) İLÇE EŞLEME ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.saha_ilce_esleme (
  ham   text PRIMARY KEY,          -- core.tr_anahtar geçmiş hali
  ilce  text NOT NULL,             -- resmî Ankara ilçesi
  cesit text NOT NULL              -- ILCE | SEMT | IL | IL_DISI
);

-- Ankara'nın 25 resmî ilçesi. Kendileriyle eşlenir ki yazım farkları
-- ('ÇANKAYA', 'Cankaya', 'çankaya') tek seçenekte toplansın.
INSERT INTO core.saha_ilce_esleme (ham, ilce, cesit)
SELECT core.tr_anahtar(x), x, 'ILCE' FROM (VALUES
  ('Akyurt'),('Altındağ'),('Ayaş'),('Bala'),('Beypazarı'),('Çamlıdere'),
  ('Çankaya'),('Çubuk'),('Elmadağ'),('Etimesgut'),('Evren'),('Gölbaşı'),
  ('Güdül'),('Haymana'),('Kahramankazan'),('Kalecik'),('Keçiören'),
  ('Kızılcahamam'),('Mamak'),('Nallıhan'),('Polatlı'),('Pursaklar'),
  ('Sincan'),('Şereflikoçhisar'),('Yenimahalle')
) v(x)
ON CONFLICT (ham) DO UPDATE SET ilce = EXCLUDED.ilce, cesit = EXCLUDED.cesit;

-- Semtler ilçelerine bağlanır. Semt ilçe değildir ama kullanıcı semt
-- yazan kaydı da ilçesinden bulabilmeli.
INSERT INTO core.saha_ilce_esleme (ham, ilce, cesit)
SELECT core.tr_anahtar(s), i, 'SEMT' FROM (VALUES
  ('Batıkent','Yenimahalle'), ('İvedik','Yenimahalle'),
  ('İvedik OSB','Yenimahalle'), ('Demetevler','Yenimahalle'),
  ('Çayyolu','Çankaya'), ('Ümitköy','Çankaya'), ('Çukurambar','Çankaya'),
  ('Söğütözü','Çankaya'), ('Kızılay','Çankaya'), ('Bahçelievler','Çankaya'),
  ('Balgat','Çankaya'), ('Dikmen','Çankaya'), ('Oran','Çankaya'),
  ('Çiğdem Mahallesi','Çankaya'), ('Yıldız','Çankaya'),
  ('Ulus','Altındağ'), ('Siteler','Altındağ'),
  ('İncek','Gölbaşı'), ('Eryaman','Etimesgut'), ('Elvankent','Etimesgut'),
  ('Ostim','Yenimahalle'), ('Sanayi','Altındağ')
) v(s, i)
ON CONFLICT (ham) DO NOTHING;

-- İl ve bölge adları: ilçe DEĞİL. Eşlenmezler, ama 'bilinmiyor' ile
-- 'kaynak il yazmış'ı ayırt edebilmek için kayıtlıdırlar.
INSERT INTO core.saha_ilce_esleme (ham, ilce, cesit) VALUES
  (core.tr_anahtar('Ankara'),              'Ankara',  'IL'),
  (core.tr_anahtar('İç Anadolu Bölgesi'),  'Ankara',  'IL'),
  (core.tr_anahtar('Türkiye'),             'Ankara',  'IL')
ON CONFLICT (ham) DO NOTHING;

-- Başka illerin ilçeleri: kaynak veri hatası. Koordinat Ankara
-- çerçevesinde olduğu için kayıt bizde kalır, ama ilçesi YANLIŞ bilinir --
-- doğrusunu bilmiyoruz, uydurmayız.
INSERT INTO core.saha_ilce_esleme (ham, ilce, cesit)
SELECT core.tr_anahtar(x), x, 'IL_DISI' FROM (VALUES
  ('Milas'),('Nilüfer'),('Şehitkamil'),('Ortaköy'),('Sarıkaya'),('Olukpınar')
) v(x)
ON CONFLICT (ham) DO NOTHING;

-- 3) HEDEF DIŞI KALIPLAR ----------------------------------------------------
CREATE TABLE IF NOT EXISTS core.saha_disla_kalip (
  kalip text PRIMARY KEY,          -- POSIX regex, kelime sınırlı
  neden text NOT NULL,
  ekleyen text NOT NULL DEFAULT 'sistem',
  eklendi timestamptz NOT NULL DEFAULT now()
);

-- 🔴 HER KALIP ÖBEK OLMAK ZORUNDA. Tek kelimelik 'oto' yazsaydık
-- 'Prof Dr M Ali Oto' adlı hekim de elenirdi.
INSERT INTO core.saha_disla_kalip (kalip, neden) VALUES
  ('(^|[^[:alnum:]])oto[[:space:]]*kuaf',        'otomotiv: oto kuaför araç temizliğidir'),
  ('(^|[^[:alnum:]])oto[[:space:]]*y[ıi]kama',   'otomotiv: oto yıkama'),
  ('(^|[^[:alnum:]])oto[[:space:]]*sanayi',      'otomotiv: sanayi sitesi'),
  ('(^|[^[:alnum:]])oto[[:space:]]*servis',      'otomotiv: araç servisi'),
  ('(^|[^[:alnum:]])oto[[:space:]]*d[öo][şs]eme', 'otomotiv: oto döşeme'),
  ('(^|[^[:alnum:]])oto[[:space:]]*galeri',      'otomotiv: araç galerisi'),
  ('(^|[^[:alnum:]])oto[[:space:]]*ekspertiz',   'otomotiv: araç ekspertizi'),
  ('(^|[^[:alnum:]])oto[[:space:]]*kiralama',    'otomotiv: araç kiralama'),
  ('(^|[^[:alnum:]])oto[[:space:]]*elektrik',    'otomotiv: oto elektrik'),
  ('otomotiv',                                   'otomotiv sektörü'),
  ('rent[[:space:]]*-?[[:space:]]*a[[:space:]]*-?[[:space:]]*car', 'araç kiralama'),
  ('ara[çc][[:space:]]+kiralama',                'araç kiralama'),
  ('(^|[^[:alnum:]])lastik([^[:alnum:]]|$)',     'otomotiv: lastik'),
  ('(^|[^[:alnum:]])kaporta',                    'otomotiv: kaporta'),
  ('(^|[^[:alnum:]])egzoz',                      'otomotiv: egzoz'),
  ('car[[:space:]]*wash',                        'otomotiv: araç yıkama')
ON CONFLICT (kalip) DO UPDATE SET neden = EXCLUDED.neden;

COMMIT;
