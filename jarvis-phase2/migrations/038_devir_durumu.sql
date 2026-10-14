-- DEVİR DURUMU — bir konuşma Jarvis'te mi, sahipte mi?
--
-- Sahip 15.10.2026: "jarvis mesajlara cevap versin, gerektiğinde bana
-- devretsin ben konuşayım." Devir kavramı bugüne kadar kodda HİÇ YOKTU;
-- konuşmanın kimde olduğunu tutan bir alan da yoktu.
--
-- NEDEN AYRI SÜTUN, `notlar` JSONB DEĞİL
-- `konusma.notlar` serbest JSONB ve içinde ne olduğu şemayla korunmuyor.
-- Devir durumu bir KAPI: yanlış okunursa müşteri şikâyeti Jarvis'e
-- cevaplatılır. Kapının değeri CHECK ile kısıtlanmalı ki geçersiz bir
-- durum yazılamasın.
--
-- VARSAYILAN NEDEN 'JARVIS' DEĞİL 'INSANDA'
-- 🔴 Bilinçli. Mevcut 2.850 mesajın hiçbiri devir kapısından geçmedi ve
-- 783'ünün sınıfı boş. Varsayılanı 'JARVIS' yapmak, geçmiş konuşmaların
-- tamamını bir anda otomatik cevaplanabilir ilan etmek olurdu. Yeni
-- konuşmalar devir kapısının kararıyla JARVIS'e geçer -- toplu değil,
-- tek tek ve sebebiyle.

BEGIN;

ALTER TABLE lcarlie.konusma
  ADD COLUMN IF NOT EXISTS devir_durumu text NOT NULL DEFAULT 'INSANDA',
  ADD COLUMN IF NOT EXISTS devir_sebep  text,
  ADD COLUMN IF NOT EXISTS devir_zaman  timestamptz;

-- Geçersiz durum yazılamaz. Kapının anlamı buna dayanıyor.
ALTER TABLE lcarlie.konusma
  DROP CONSTRAINT IF EXISTS konusma_devir_durumu_gecerli;
ALTER TABLE lcarlie.konusma
  ADD CONSTRAINT konusma_devir_durumu_gecerli
  CHECK (devir_durumu IN ('JARVIS', 'INSANDA', 'KAPALI'));

COMMENT ON COLUMN lcarlie.konusma.devir_durumu IS
  'JARVIS: Jarvis cevaplayabilir. INSANDA: yalniz sahip cevaplar. KAPALI: konusma bitti.';
COMMENT ON COLUMN lcarlie.konusma.devir_sebep IS
  'jarvis.devir sebep kodu: SAGLIK_SIKAYET, ISLEM, URUN_BELIRSIZ, MEVZUAT, SINIF_YOK';
COMMENT ON COLUMN lcarlie.konusma.devir_zaman IS
  'Devir durumunun son degistigi an.';

-- Panelin ilk sorgusu "sahipte bekleyenler" olacak; indeks ona gore.
CREATE INDEX IF NOT EXISTS konusma_devir_bekleyen
  ON lcarlie.konusma (devir_durumu, son_mesaj DESC);

COMMIT;
