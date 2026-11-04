-- Gmail ekstre okuması sayfalı (02.11.2026): okunan mail bir daha indirilmez, boş ekstre 0 satırla saklanır.
BEGIN;
ALTER TABLE core.jarvis_money_upload ADD COLUMN IF NOT EXISTS gmail_message text
    CHECK (gmail_message IS NULL OR gmail_message ~ '^[0-9a-f]{8,40}$');
CREATE INDEX IF NOT EXISTS jarvis_money_upload_gmail ON core.jarvis_money_upload (owner, gmail_message)
    WHERE gmail_message IS NOT NULL;
GRANT UPDATE (gmail_message, line_count) ON core.jarvis_money_upload TO jarvis_web;

-- QNB KMH dönem ekstresi, günlük "Hesap Hareketleri" ile AYNI hesap: Temmuz'un 13–31'i iki kez sayılıyordu.
-- İkizi olan KMH satırı silinir (bağlantılar günlük satırlarda), kalanı tek hesap adına geçer.
WITH k AS (SELECT movement_id, tx_date, direction, amount_cents,
                  row_number() OVER (PARTITION BY tx_date, direction, amount_cents ORDER BY movement_id) n
           FROM core.jarvis_money_movement WHERE book='lemos' AND account='QNB KMH hesabı · Lemos şirket'),
     b AS (SELECT tx_date, direction, amount_cents,
                  row_number() OVER (PARTITION BY tx_date, direction, amount_cents ORDER BY movement_id) n
           FROM core.jarvis_money_movement WHERE book='lemos' AND account='QNB Bereketli Ticari Hesap · Lemos şirket')
DELETE FROM core.jarvis_money_movement m USING k JOIN b USING (tx_date, direction, amount_cents, n)
 WHERE m.movement_id = k.movement_id;
UPDATE core.jarvis_money_movement SET account='QNB Bereketli Ticari Hesap · Lemos şirket', updated_at=clock_timestamp()
 WHERE book='lemos' AND account='QNB KMH hesabı · Lemos şirket';
UPDATE core.jarvis_money_movement
   SET party=regexp_replace(party, '^\w+ İşlemleri - ', ''), updated_at=clock_timestamp()
 WHERE book='lemos' AND party ~ '^\w+ İşlemleri - ';
-- Kişisel kurallar (Meral/Murat = gelir desteği, kişisel) Lemos defterine sızmıştı: aileden ŞİRKETE gelen para.
UPDATE core.jarvis_money_movement SET category='aile_gelen', scope='lemos', updated_at=clock_timestamp()
 WHERE book='lemos' AND scope IN ('kisisel','aile') AND direction='in';
UPDATE core.jarvis_money_movement  -- money_ledger.key_of() of the two names
   SET party_key=CASE party WHEN 'Faiz Tahakkuku' THEN 'faiztahakkuku' ELSE 'bsmvkesintisi' END
 WHERE book='lemos' AND party IN ('Faiz Tahakkuku', 'BSMV Kesintisi');
COMMIT;
