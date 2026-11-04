-- Gercek konusmalardan SORU -> CEVAP kaliplarini cikarir.
-- Kural dayatmaz; ne yapildiysa onu sayar. Ajan buradan kendi algoritmasini okur.

CREATE TABLE IF NOT EXISTS lcarlie.kalip (
  id            bigserial PRIMARY KEY,
  soru_norm     text NOT NULL,
  cevap_imza    text NOT NULL,
  adet          integer NOT NULL,
  oran          numeric(5,2),
  ornek_soru    text,
  ornek_cevap   text,
  gecikme_sn    integer,
  uretim        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (soru_norm, cevap_imza)
);

-- Normalizasyon: kucuk harf, noktalama ve fazla bosluk temizligi
CREATE OR REPLACE FUNCTION lcarlie.norm(t text) RETURNS text AS $$
  SELECT btrim(regexp_replace(lower(coalesce(t,'')), '[^a-zçğıöşü0-9 ]+', ' ', 'g'));
$$ LANGUAGE sql IMMUTABLE;

-- Her musteri mesajina, ayni konusmada ondan SONRAKI ilk isletme mesajini esle
CREATE OR REPLACE VIEW lcarlie.v_soru_cevap AS
SELECT s.konusma_id,
       s.zaman                AS soru_zaman,
       s.metin                AS soru,
       c.metin                AS cevap,
       EXTRACT(EPOCH FROM (c.zaman - s.zaman))::int AS gecikme_sn
FROM lcarlie.mesaj s
CROSS JOIN LATERAL (
  SELECT m.metin, m.zaman
  FROM lcarlie.mesaj m
  WHERE m.konusma_id = s.konusma_id
    AND m.gonderen = 'insan'
    AND m.zaman > s.zaman
  ORDER BY m.zaman
  LIMIT 1
) c
WHERE s.gonderen = 'musteri'
  AND length(btrim(s.metin)) > 2
  AND length(btrim(c.metin)) > 2;

-- Kaliplari doldur (her calistirmada tazelenir)
TRUNCATE lcarlie.kalip;

INSERT INTO lcarlie.kalip (soru_norm, cevap_imza, adet, ornek_soru, ornek_cevap, gecikme_sn)
SELECT lcarlie.norm(soru)                AS soru_norm,
       left(btrim(cevap), 60)            AS cevap_imza,
       count(*)                          AS adet,
       min(soru)                         AS ornek_soru,
       min(cevap)                        AS ornek_cevap,
       (percentile_disc(0.5) WITHIN GROUP (ORDER BY gecikme_sn))::int AS gecikme_sn
FROM lcarlie.v_soru_cevap
GROUP BY 1,2;

-- Oran: ayni soru icin bu cevabin payi
UPDATE lcarlie.kalip k
SET oran = ROUND(100.0 * k.adet / t.toplam, 2)
FROM (SELECT soru_norm, sum(adet) AS toplam FROM lcarlie.kalip GROUP BY 1) t
WHERE k.soru_norm = t.soru_norm;
