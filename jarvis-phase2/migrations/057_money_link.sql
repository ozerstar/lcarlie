-- Para akışı eşleşmesi (sahip, 02.11.2026): gelen para 0-2 gün içinde çıkanlarla eşlenir.
-- aracilik = başkası adına geçti (gelir de gider de sayılmaz); kullanim = yalnız açıklama.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_money_link (
    owner text NOT NULL,
    in_id text NOT NULL,
    out_id text NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    kind text NOT NULL CHECK (kind IN ('aracilik','kullanim')),
    status text NOT NULL DEFAULT 'auto' CHECK (status IN ('auto','ok','rejected')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, in_id, out_id)
);
CREATE INDEX IF NOT EXISTS jarvis_money_link_out ON core.jarvis_money_link (owner, out_id);
REVOKE ALL ON core.jarvis_money_link FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.jarvis_money_link TO jarvis_web;
-- Muharrem Murat / Meral Yıldız'dan gelen = gelir desteği (maaş), kişisel
INSERT INTO core.jarvis_money_rule (owner, party_key, direction, label, category, scope)
SELECT DISTINCT ON (owner, party_key) owner, party_key, 'in', party, 'gelir_destegi', 'kisisel'
  FROM core.jarvis_money_movement
 WHERE direction='in' AND party_key IN ('muharremmuratyildiz','meralyildiz')
ON CONFLICT (owner, party_key, direction) DO UPDATE
   SET category='gelir_destegi', scope='kisisel', updated_at=clock_timestamp();
COMMIT;
