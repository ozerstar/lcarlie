-- lcarlie YEREL: schema-only dump VERI icermedigi icin f4/f5/f6'nin yazdigi referans satirlari
-- burada aynen tekrar edilir. Orijinal kaynaklar:
--   f4-apply.sql  -> core.ai_action_type 6 satir (execution_enabled=false)
--   f5-apply.sql  -> UPDATE ... execution_enabled=true WHERE action_type='REQUEST_HUMAN_REVIEW'
--   f6-apply.sql  -> core.ai_orchestrator_config 3 anahtar (ai_worker_enabled=false = kill-switch KAPALI)
--   lcarlie-first-task.sql -> cutoff_version 'f0b-20260917' (enqueue cagrisinda kullanilan deger)
-- 'orchestrator_enabled_after' F0-B'de tanimli ama degeri hicbir dosyada yok: BILEREK eklenmedi.
-- (NULL iken ai_claim_task yalnizca ai_enqueue=true olan gorevleri alir: kapali-varsayilan.)
BEGIN;
INSERT INTO core.ai_action_type(action_type,risk_class,approval_mode,schema_version,description) VALUES
('REQUEST_HUMAN_REVIEW','LOW','ONE_PERSON','v1','Create a human review request only'),
('DRAFT_CUSTOMER_REPLY','MEDIUM','ONE_PERSON','v1','Draft a reply without sending it'),
('WHATSAPP_SEND_TEMPLATE','HIGH','ONE_PERSON','v1','Propose a template send; execution disabled in F4'),
('META_CAMPAIGN_CHANGE','HIGH','ONE_PERSON','v1','Propose pause or resume; execution disabled in F4'),
('WIX_PUBLISH','CRITICAL','TWO_PERSON','v1','Propose publish; execution disabled in F4'),
('PRICE_CHANGE','CRITICAL','TWO_PERSON','v1','Propose price change; execution disabled in F4')
ON CONFLICT (action_type) DO NOTHING;
UPDATE core.ai_action_type SET execution_enabled=true WHERE action_type='REQUEST_HUMAN_REVIEW';

INSERT INTO core.ai_orchestrator_config(config_key,config_value,description) VALUES
('ai_worker_enabled','false','Production kill-switch; remains false until a real provider is configured'),
('action_worker_enabled','true','Enables only allowlisted internal execution handlers'),
('runtime_generation','f6-20260917','Current scheduler/runtime generation'),
('cutoff_version','f0b-20260917','YEREL: lcarlie-first-task.sql icindeki cutoff degeri')
ON CONFLICT (config_key) DO NOTHING;
COMMIT;
