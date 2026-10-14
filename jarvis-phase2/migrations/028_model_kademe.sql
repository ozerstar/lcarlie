-- 028 — MODEL KADEMESİ KAYDI: hangi iş hangi modelle yapılır (22.09.2026)
--
-- Sahip: *"mantıklı olan hangisi ise öyle yap, önemli olan doğru iş için
-- doğru iş modelini kullanabilmek"* ve *"bunu ayıracak bir repo varsa onu
-- da kur ve planlamayı o yapsın, AI ve motor sorumlusu."*
--
-- ÖLÇÜLEN DURUM — NEDEN GEREKLİ
-- Altı çağrı yerinin dördü kodda `escalate=True` yazıyordu (satış diyaloğu,
-- satış öğrenme, günlük bülten, kreatif brief) ama zincir her seferinde
-- gemini'den başlayıp ilk cevapta durduğu için istek HİÇ karşılanmadı.
-- Defter: 79 gemini çağrısına karşılık 1 claude. Yani sistemin müşteriye
-- giden metinleri en küçük modelle üretiliyordu ve bu hiçbir yerde
-- görünmüyordu.
--
-- 🔴 ATAMA KODDA GÖMÜLÜ KALMAMALI. Gömülü kalırsa değiştirmek için kod
-- dağıtımı gerekir, kimin neden değiştirdiği kaybolur ve panelden
-- görünmez. Burada durunca: kim, ne zaman, hangi gerekçeyle atadı yazılı
-- kalır ve motor sorumlusu bunu ölçüme dayanarak revize edebilir.
--
-- 🔴 KOD YİNE DE SUSMAZ. `providers.py` bu tabloyu okuyamazsa kendi
-- gömülü varsayılanına düşer. Veritabanı erişilemez diye Jarvis'in
-- konuşamaz hale gelmesi, yanlış kademede konuşmasından daha kötüdür.
--
-- 🔴 İNSAN BEYANI DEĞİL, MÜHENDİSLİK KARARI. Bu tabloyu `ai_writer`
-- YAZABİLİR -- `core.gonderi_notu`dan farkı bu: orada insanın beyanı
-- kaydediliyordu, burada ölçülebilir bir yapılandırma tutuluyor. Yine de
-- yürürlüğe girmesi onaya bağlı: motor sorumlusu ÖNERİ üretir.
--
-- Geri alma: migrations/rollback/028_model_kademe_ROLLBACK.sql

BEGIN;

CREATE TABLE IF NOT EXISTS core.model_kademe (
    is_anahtari  text        PRIMARY KEY,   -- 'satis_dialog', 'kreatif_brief'…
    kademe       text        NOT NULL,
    gerekce      text        NOT NULL,      -- NEDEN bu kademe; boş geçilemez
    -- Riskin ne olduğu: yanlış cevabın bedeli nereye düşer.
    risk         text        NOT NULL DEFAULT 'IC',
    atayan       text        NOT NULL,
    atandi       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT model_kademe_gecerli CHECK (kademe IN ('hizli', 'muhakeme')),
    CONSTRAINT model_kademe_risk CHECK (risk IN ('MUSTERIYE', 'KARARA', 'IC')),
    -- Gerekçesiz atama, sonraki kişinin değiştiremeyeceği bir atamadır.
    CONSTRAINT model_kademe_gerekce CHECK (length(btrim(gerekce)) >= 12)
);

COMMENT ON TABLE core.model_kademe IS
 'Hangi işin hangi model kademesinde çalışacağı. Kod bunu okur; '
 'okuyamazsa gömülü varsayılana düşer ve susmaz.';

-- İlk doluluk: KODUN ZATEN İSTEDİĞİ atama. Kendi görüşüm değil --
-- çağrı yerlerinde yazan `escalate` değeri neyse o. Motor sorumlusu
-- bunu ölçüme dayanarak değiştirebilir.
INSERT INTO core.model_kademe (is_anahtari, kademe, gerekce, risk, atayan) VALUES
  ('satis_dialog',   'muhakeme',
   'Cevap doğrudan müşteriye gidiyor; yanlış ifade geri alınamaz ve mevzuat riski taşır. Kod zaten escalate=True istiyordu.',
   'MUSTERIYE', 'olcum-22.09.2026'),
  ('satis_ogrenme',  'muhakeme',
   'Üretilen yönerge sonraki bütün müşteri cevaplarını şekillendiriyor; hata tek seferlik değil, kalıcı.',
   'KARARA', 'olcum-22.09.2026'),
  ('guncel_olaylar', 'muhakeme',
   'Günlük dış bülten; kaynaksız ya da uydurma madde doğrudan yanlış karar besler.',
   'KARARA', 'olcum-22.09.2026'),
  ('kreatif_brief',  'muhakeme',
   'Reklam metni ve görsel yönergesi üretiyor; çıktısı yayına giden materyale dönüşüyor.',
   'MUSTERIYE', 'olcum-22.09.2026'),
  ('tasarim_gorevi', 'muhakeme',
   'Ölçülebilir arayüz şartnamesi üretiyor ve kırmızı takım denetiminden geçiyor; muhakeme gerektirir.',
   'KARARA', 'olcum-22.09.2026'),
  ('query_planner',  'hizli',
   'Araştırma sorgusu üretir; yanlışsa bir sonraki koşuda düzelir ve kimseye gitmez. Yüksek hacim.',
   'IC', 'olcum-22.09.2026'),
  ('sohbet',         'hizli',
   'Panel sohbeti etkileşimli; gecikme doğrudan hissediliyor ve cevap kanıta bağlı zaten denetleniyor.',
   'IC', 'olcum-22.09.2026')
ON CONFLICT (is_anahtari) DO NOTHING;

CREATE OR REPLACE VIEW mart.model_kademe_guncel AS
SELECT is_anahtari, kademe, risk, gerekce, atayan, atandi
  FROM core.model_kademe
 ORDER BY (kademe = 'muhakeme') DESC, is_anahtari;

GRANT SELECT ON core.model_kademe, mart.model_kademe_guncel TO ai_reader;
-- Mühendislik yapılandırması: makine önerir, okur ve yazabilir.
GRANT SELECT, INSERT, UPDATE ON core.model_kademe TO ai_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.model_kademe TO human_approver;

COMMIT;
