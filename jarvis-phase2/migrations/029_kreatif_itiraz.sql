-- 029 — KREATİF İTİRAZI: "bu görselde logo yanlış, kiminle konuşacağım?"
--
-- Sahip 22.09.2026: *"kreatif sayfasına girdim, burada yapılan çalışmalar
-- hakkında kiminle konuşacağım? mesela ikinci görselde logo yanlış, ürün
-- yanlış — bununla ilgili kiminle konuşacağız?"*
--
-- DÜRÜST CEVAP: ŞU ANA KADAR HİÇ KİMSEYLE.
-- Panel görseli gösteriyordu, altında dört departmanın kararı da duruyordu
-- (GRAFIK_TASARIM, KREATIF_DIREKTOR, MARKA, MEVZUAT) ama sahibin o karara
-- itiraz etmesinin, bir muhatap bulmasının ve cevabı takip etmesinin
-- hiçbir yolu yoktu. Görsel beğenilmezse tek seçenek partiyi reddetmekti;
-- NEDEN beğenilmediği hiçbir yere yazılmıyordu, dolayısıyla bir sonraki
-- koşu aynı hatayı tekrarlıyordu.
--
-- 🔴 MUHATAP SEÇİLMEZ, TÜRETİLİR. Sahibe "kime soralım?" diye sormak,
-- cevabı bilmesi gereken tarafın sistem olduğu bir soruyu ona yüklemek
-- olurdu. Konu seçilir (logo/ürün/metin/marka), muhatap o görseli
-- GERÇEKTEN inceleyen departmanlardan bulunur. İnceleyen yoksa panel
-- "bu görseli o departman incelememiş" der -- uydurulmuş bir muhatap
-- yazmaz.
--
-- 🔴 İTİRAZI SAHİP AÇAR, MAKİNE CEVAPLAR, SAHİP KAPATIR.
-- `durum` akışı: ACIK -> CEVAPLANDI -> KAPANDI. `KAPANDI`ya yalnız
-- human_approver geçebilir; TETİKLEYİCİ ile zorlanır, sözleşmeye
-- bırakılmaz. Makinenin kendi cevabını "çözüldü" diye işaretleyebilmesi,
-- itiraz mekanizmasını anlamsız kılardı.
--
-- Geri alma: migrations/rollback/029_kreatif_itiraz_ROLLBACK.sql

BEGIN;

CREATE TABLE IF NOT EXISTS core.kreatif_itiraz (
    itiraz_id   bigserial   PRIMARY KEY,
    parti       text        NOT NULL,   -- 'hydravie-20260921-1307-gorseller'
    dosya       text,                   -- '02-4x5.jpg'; NULL = partinin tamamı
    konu        text        NOT NULL,
    aciklama    text        NOT NULL,
    -- Türetilen muhatap; hangi departmanın cevap vermesi gerektiği.
    muhatap     text        NOT NULL,
    durum       text        NOT NULL DEFAULT 'ACIK',
    cevap       text,
    cevaplayan  text,
    cevaplandi  timestamptz,
    acan        text        NOT NULL,
    acildi      timestamptz NOT NULL DEFAULT now(),
    kapatan     text,
    kapandi     timestamptz,
    CONSTRAINT kreatif_itiraz_konu CHECK (konu IN
        ('LOGO', 'URUN', 'METIN', 'MARKA', 'MEVZUAT', 'DIGER')),
    CONSTRAINT kreatif_itiraz_durum CHECK (durum IN
        ('ACIK', 'CEVAPLANDI', 'KAPANDI', 'TEKRAR_ACILDI')),
    -- Açıklamasız itiraz, muhatabın ne düzelteceğini bilmediği itirazdır.
    CONSTRAINT kreatif_itiraz_aciklama CHECK (length(btrim(aciklama)) >= 8)
);

COMMENT ON TABLE core.kreatif_itiraz IS
 'Sahibin belirli bir kreatif görsele itirazı ve muhatap departmanın '
 'cevabı. Bir sonraki koşu açık itirazları okumak zorundadır.';

CREATE INDEX IF NOT EXISTS kreatif_itiraz_parti ON core.kreatif_itiraz (parti);
CREATE INDEX IF NOT EXISTS kreatif_itiraz_acik
    ON core.kreatif_itiraz (muhatap) WHERE durum IN ('ACIK', 'TEKRAR_ACILDI');

-- 🔴 KAPATMA YETKİSİ: yalnız insan. Makine kendi cevabını "tamam" diye
-- işaretleyemez. Sözleşme değil, tetikleyici -- kod yolu değişse de kural
-- yerinde kalır.
CREATE OR REPLACE FUNCTION core.kreatif_itiraz_kapatma_kontrol()
RETURNS trigger LANGUAGE plpgsql AS $gate$
BEGIN
    IF NEW.durum = 'KAPANDI' AND (OLD.durum IS DISTINCT FROM 'KAPANDI')
       AND current_user <> 'human_approver' THEN
        RAISE EXCEPTION
            'itirazı yalnız human_approver kapatabilir (deneyen: %)', current_user;
    END IF;
    RETURN NEW;
END;
$gate$;

DROP TRIGGER IF EXISTS kreatif_itiraz_kapatma ON core.kreatif_itiraz;
CREATE TRIGGER kreatif_itiraz_kapatma
    BEFORE UPDATE ON core.kreatif_itiraz
    FOR EACH ROW EXECUTE FUNCTION core.kreatif_itiraz_kapatma_kontrol();

-- Panel görünümü: açık itirazlar önce, en yenisi üstte.
CREATE OR REPLACE VIEW mart.kreatif_itiraz_guncel AS
SELECT itiraz_id, parti, dosya, konu, aciklama, muhatap, durum,
       cevap, cevaplayan, cevaplandi, acan, acildi, kapatan, kapandi,
       (durum IN ('ACIK', 'TEKRAR_ACILDI')) AS acik_mi,
       EXTRACT(DAY FROM (now() - acildi))::int AS gun_gecti
  FROM core.kreatif_itiraz
 ORDER BY (durum IN ('ACIK', 'TEKRAR_ACILDI')) DESC, acildi DESC;

GRANT SELECT ON core.kreatif_itiraz, mart.kreatif_itiraz_guncel TO ai_reader;
-- Makine CEVAP yazar (kapatamaz; tetikleyici engelliyor).
GRANT SELECT, UPDATE ON core.kreatif_itiraz TO ai_writer;
-- İtirazı sahip açar ve kapatır.
GRANT SELECT, INSERT, UPDATE ON core.kreatif_itiraz TO human_approver;
GRANT USAGE ON SEQUENCE core.kreatif_itiraz_itiraz_id_seq TO human_approver;

COMMIT;
