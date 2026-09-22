-- 025 — ARAŞTIRMA PLANI: kapsam koddan çıkıp karara geçer (21.09.2026)
--
-- SORUN (ölçüldü)
-- `scripts/departman-arastirma.py` içindeki `KONULAR` sözlüğü kapsamı
-- SABİTLİYORDU: 45 departmanın 6'sı, konular elle yazılmış. Ürün başına
-- düzenli araştırma hiç yoktu. Yeni bir ürün eklendiğinde ya da bir
-- departman kadro aldığında hiçbir şey değişmiyordu -- çünkü planı kimse
-- yapmıyordu, kod yapıyordu.
--
-- ÇÖZÜM
-- Plan bir TABLOYA taşınır. İş Planlama Müdürü (roster: is_planlama,
-- 21.09.2026'da kadroya eklendi) kapsamı ölçer ve satırları yazar;
-- zamanlayıcı bu tabloyu okur. Kapsamı değiştirmek artık kod değişikliği
-- değil, plan değişikliğidir.
--
-- 🔴 PLAN BİR BEYAN DEĞİL, BİR NİYETTİR. Bu yüzden ai_writer yazabilir.
-- Ölçüm ve insan beyanı tabloları (core.pazar_bulgu, core.kreatif_karar)
-- ai_writer'a KAPALI kalmaya devam eder; burada karıştırma yok.
--
-- Geri alma: migrations/rollback/025_arastirma_plani_ROLLBACK.sql

BEGIN;

CREATE TABLE IF NOT EXISTS core.arastirma_plani (
    plan_id      bigserial PRIMARY KEY,
    kapsam       text        NOT NULL,   -- DEPARTMAN | URUN
    hedef        text        NOT NULL,   -- departman kodu ya da ürün adı
    konu         text        NOT NULL,   -- aranacak konu
    siklik_gun   integer     NOT NULL,   -- kaç günde bir
    oncelik      integer     NOT NULL DEFAULT 5,   -- 1 en yüksek
    gerekce      text        NOT NULL,   -- NEDEN bu konu, bu sıklıkta
    planlayan    text        NOT NULL DEFAULT 'is_planlama',
    olusturuldu  timestamptz NOT NULL DEFAULT now(),
    aktif        boolean     NOT NULL DEFAULT true,
    son_kosu     timestamptz,
    son_bulgu    integer     NOT NULL DEFAULT 0,
    CONSTRAINT arastirma_plani_kapsam CHECK (kapsam IN ('DEPARTMAN', 'URUN')),
    CONSTRAINT arastirma_plani_siklik CHECK (siklik_gun BETWEEN 1 AND 90),
    CONSTRAINT arastirma_plani_oncelik CHECK (oncelik BETWEEN 1 AND 9),
    -- Aynı hedefe aynı konuyu iki kez planlamak, aynı aramayı iki kez
    -- koşturup faturayı ikiye katlar.
    CONSTRAINT arastirma_plani_tekil UNIQUE (kapsam, hedef, konu)
);

COMMENT ON TABLE core.arastirma_plani IS
 'Hangi birim/ürün, neyi, hangi sıklıkta araştıracak. İş Planlama Müdürü '
 'yazar, zamanlayıcı okur. Kapsam artık kodda değil burada.';

-- Sıradaki iş: süresi dolmuş, öncelikli satırlar önce.
CREATE OR REPLACE VIEW mart.arastirma_sirasi AS
SELECT p.*,
       (p.son_kosu IS NULL) AS hic_kosmadi,
       CASE WHEN p.son_kosu IS NULL THEN 999999
            ELSE EXTRACT(DAY FROM (now() - p.son_kosu))::int
       END AS gun_gecti,
       CASE WHEN p.son_kosu IS NULL THEN TRUE
            ELSE now() - p.son_kosu > (p.siklik_gun || ' days')::interval
       END AS vakti_geldi
  FROM core.arastirma_plani p
 WHERE p.aktif
 ORDER BY (p.son_kosu IS NULL) DESC, p.oncelik, p.son_kosu NULLS FIRST;

GRANT SELECT ON core.arastirma_plani, mart.arastirma_sirasi TO ai_reader;
GRANT SELECT, INSERT, UPDATE ON core.arastirma_plani TO ai_writer;
GRANT USAGE ON SEQUENCE core.arastirma_plani_plan_id_seq TO ai_writer;
-- Sahip planı görebilsin ve gerekirse kapatabilsin.
GRANT SELECT, INSERT, UPDATE, DELETE ON core.arastirma_plani TO human_approver;
GRANT USAGE ON SEQUENCE core.arastirma_plani_plan_id_seq TO human_approver;

COMMIT;

