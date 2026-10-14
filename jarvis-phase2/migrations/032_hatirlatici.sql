-- 032 — KİŞİSEL ASİSTAN: hatırlatıcılar
--
-- Sahip 22.09.2026: *"kişisel asistanımı farklı bir bölümde, hatırlatıcılar
-- ve haberleri ana sayfada görebilmek istiyorum, buranın düzeni önemli."*
--
-- 🔴 BU TABLO ŞİRKET VERİSİ DEĞİL, SAHİBİN KENDİ NOTU. Diğer tablolarda
-- makine yazar insan onaylar; burada tam tersi: İNSAN yazar, makine
-- yalnız okur ve zamanı gelince gösterir. `ai_writer`a INSERT verilmiyor.
--
-- 🔴 HATIRLATICI METNİ PII TAŞIYABİLİR. Sahip "Ahmet Bey'i ara" yazabilir.
-- Bu yüzden metin CompanyMemory sorgularına AÇILMIYOR; yalnız panel
-- okur. Aynı kural müşteri mesajlarında da geçerliydi.
--
-- 🔴 TEKRAR EDEN HATIRLATICI "bitti" OLMAZ. `tekrar` dolu olan satır
-- tamamlandığında bir SONRAKİ tarihe ötelenir; kapatılmaz. Aksi halde
-- "her ay fatura" gibi bir madde bir kez yapılınca kaybolurdu.
--
-- Geri alma: migrations/rollback/032_hatirlatici_ROLLBACK.sql

BEGIN;

CREATE TABLE IF NOT EXISTS core.hatirlatici (
    id          bigserial   PRIMARY KEY,
    baslik      text        NOT NULL,
    not_        text,
    -- Ne zaman hatırlatılacak.
    zaman       timestamptz NOT NULL,
    -- 'gunluk' | 'haftalik' | 'aylik' | NULL (tek seferlik)
    tekrar      text,
    onem        text        NOT NULL DEFAULT 'NORMAL',
    durum       text        NOT NULL DEFAULT 'ACIK',
    -- Kim yazdı: sahip mi, sistem mi (ör. jeton bütçesi uyarısı).
    kaynak      text        NOT NULL DEFAULT 'sahip',
    tamamlandi  timestamptz,
    olusturma   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT hatirlatici_baslik_dolu CHECK (length(trim(baslik)) >= 2),
    CONSTRAINT hatirlatici_durum_izinli
        CHECK (durum IN ('ACIK', 'TAMAM', 'IPTAL')),
    CONSTRAINT hatirlatici_onem_izinli
        CHECK (onem IN ('DUSUK', 'NORMAL', 'YUKSEK')),
    CONSTRAINT hatirlatici_tekrar_izinli
        CHECK (tekrar IS NULL OR tekrar IN ('gunluk', 'haftalik', 'aylik'))
);

CREATE INDEX IF NOT EXISTS hatirlatici_acik_zaman
    ON core.hatirlatici (zaman) WHERE durum = 'ACIK';

-- Panel görünümü: zamanı gelenler önce, gecikenler işaretli.
CREATE OR REPLACE VIEW mart.hatirlatici_guncel AS
SELECT id, baslik, not_, zaman, tekrar, onem, durum, kaynak, olusturma,
       (durum = 'ACIK' AND zaman <= now())            AS zamani_geldi,
       (durum = 'ACIK' AND zaman <  now() - interval '1 day') AS gecikti,
       EXTRACT(EPOCH FROM (zaman - now()))::bigint    AS kalan_sn
  FROM core.hatirlatici
 WHERE durum = 'ACIK'
 ORDER BY zaman;

-- 🔴 ai_writer YOK. Bu tabloya makine yazmaz; sahibin kendi notu.
GRANT SELECT ON core.hatirlatici, mart.hatirlatici_guncel TO ai_reader;
GRANT SELECT, INSERT, UPDATE ON core.hatirlatici TO human_approver;
GRANT USAGE ON SEQUENCE core.hatirlatici_id_seq TO human_approver;

COMMIT;
