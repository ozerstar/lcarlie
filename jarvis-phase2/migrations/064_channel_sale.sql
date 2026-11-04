-- Kanal satışları (Wix + Trendyol) faturalarla tek toplamda (sahip, 02.11.2026: "buradaki satışlarla
-- Trendyol ve Wix satışlarını birleştirip toplam satışı göreceğiz").
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_channel_sale (
    owner               text NOT NULL,
    channel             text NOT NULL CHECK (channel IN ('wix','trendyol')),
    order_no            text NOT NULL,
    line_no             text NOT NULL,
    kind                text NOT NULL CHECK (kind IN ('sale','return','discount','shipping')),
    sale_date           date NOT NULL,
    customer            text NOT NULL DEFAULT '',
    item                text NOT NULL DEFAULT '',
    quantity            numeric NOT NULL DEFAULT 0,
    gross_cents         bigint NOT NULL,
    net_cents           bigint NOT NULL,
    vat_assumed         boolean NOT NULL DEFAULT false,
    product             text NOT NULL DEFAULT '',
    business            text NOT NULL DEFAULT 'lcarlie',
    invoice_document_id text,
    fetched_at          timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner, channel, order_no, line_no, kind)
);
CREATE INDEX IF NOT EXISTS jarvis_channel_sale_day ON core.jarvis_channel_sale (owner, sale_date);
GRANT SELECT, INSERT, UPDATE, DELETE ON core.jarvis_channel_sale TO jarvis_web;
-- TYA faturası Trendyol sipariş numarasını taşır: sipariş ↔ fatura birebir
ALTER TABLE core.jarvis_invoice ADD COLUMN IF NOT EXISTS order_no text NOT NULL DEFAULT '';
-- Wix siparişleri ve Trendyol ürün adları ham katmanda: yalnız okuma
GRANT USAGE ON SCHEMA raw TO jarvis_web;
GRANT SELECT ON raw.wix_order, raw.wix_order_item, raw.trendyol_urun TO jarvis_web;
COMMIT;
