-- L'CARLIÉ ürün maliyet / kâr tablosu: "Harcama ekle" ile girilen maliyetler (sahip, 02.11.2026:
-- "eklenen her maliyet genel maliyet kalemine etki etsin, veya seçtiğim ürünün maliyetine").
-- Faturadan gelen maliyetler burada değil, faturalarda; bu tablo yalnız elle eklenenler.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_product_cost (
    cost_id     text PRIMARY KEY CHECK (cost_id ~ '^[0-9a-f]{32}$'),
    owner       text NOT NULL,
    spent_on    date NOT NULL,
    description text NOT NULL CHECK (length(description) BETWEEN 1 AND 200),
    net_cents   bigint NOT NULL CHECK (net_cents > 0),
    vat_cents   bigint NOT NULL DEFAULT 0 CHECK (vat_cents >= 0),
    target      text NOT NULL CHECK (target IN ('genel', 'urun')),
    product     text,
    note        text NOT NULL DEFAULT '' CHECK (length(note) <= 300),
    created_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((target = 'urun') = (product IS NOT NULL AND product <> ''))
);
CREATE INDEX IF NOT EXISTS jarvis_product_cost_owner ON core.jarvis_product_cost (owner, spent_on);
GRANT SELECT, INSERT, DELETE ON core.jarvis_product_cost TO jarvis_web;
COMMIT;
