-- Channel/store/order identity and immutable invoice/shipment/POS observations.
-- This migration neither calls providers nor imports real customer data.
BEGIN;
CREATE TABLE IF NOT EXISTS core.jarvis_cari_source_event (
    event_id text PRIMARY KEY CHECK (event_id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    source text NOT NULL CHECK (source IN
        ('trendyol','n11','amazon','hepsiburada','wix','basitkargo','qnb_pos')),
    store_id text NOT NULL CHECK (length(store_id) BETWEEN 1 AND 160),
    object_id text NOT NULL CHECK (length(object_id) BETWEEN 1 AND 160),
    event_key text NOT NULL CHECK (length(event_key) BETWEEN 1 AND 160),
    source_updated_at timestamptz NOT NULL,
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(owner,source,store_id,event_key)
);
CREATE INDEX IF NOT EXISTS jarvis_cari_source_current
    ON core.jarvis_cari_source_event(owner,source,store_id,object_id,source_updated_at DESC);
REVOKE ALL ON core.jarvis_cari_source_event FROM PUBLIC;
REVOKE UPDATE,DELETE,TRUNCATE ON core.jarvis_cari_source_event FROM jarvis_web;
GRANT SELECT,INSERT ON core.jarvis_cari_source_event TO jarvis_web;
COMMIT;
