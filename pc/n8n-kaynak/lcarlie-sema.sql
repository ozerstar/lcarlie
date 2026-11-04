-- L'CARLIÉ konuşma veri ambarı — Faz A
-- Amaç: Meta (Instagram/WhatsApp/Messenger) konuşmalarını kalıcı ve
-- sorgulanabilir biçimde biriktirmek; ileride satış odaklı ajanın
-- eğitim/ölçüt verisi olacak.
-- Tamamen EKLEMEDİR: var olan hiçbir tabloya dokunmaz.

CREATE SCHEMA IF NOT EXISTS lcarlie;

-- ---------------------------------------------------------------
-- KONUŞMA (thread başlığı)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lcarlie.konusma (
  id            bigserial   PRIMARY KEY,
  kanal         text        NOT NULL,            -- instagram | whatsapp | messenger | web
  harici_id     text,                            -- Meta thread/conversation id
  musteri_ref   text,                            -- IGSID / telefon / oturum kimliği
  musteri_ad    text,
  ilk_mesaj     timestamptz,
  son_mesaj     timestamptz,
  mesaj_sayisi  integer     NOT NULL DEFAULT 0,
  -- satış hunisi
  sonuc         text        NOT NULL DEFAULT 'bilinmiyor',  -- siparis|kayip|acik|bilinmiyor
  siparis_no    text,                            -- Wix sipariş eşleşmesi
  siparis_tutar numeric(12,2),
  -- serbest alan: kaynak reklam, etiketler, değerlendirme notları
  notlar        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  olusturma     timestamptz NOT NULL DEFAULT now(),
  guncelleme    timestamptz NOT NULL DEFAULT now()
);

-- Aynı konuşmayı iki kez almayı imkânsız kılar (tekrar çekim güvenli)
CREATE UNIQUE INDEX IF NOT EXISTS konusma_harici_tekil
  ON lcarlie.konusma (kanal, harici_id) WHERE harici_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS konusma_kanal_zaman ON lcarlie.konusma (kanal, son_mesaj DESC);
CREATE INDEX IF NOT EXISTS konusma_sonuc       ON lcarlie.konusma (sonuc, son_mesaj DESC);
CREATE INDEX IF NOT EXISTS konusma_musteri     ON lcarlie.konusma (musteri_ref);

-- ---------------------------------------------------------------
-- MESAJ (asıl veri — tek tek mesajlar)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lcarlie.mesaj (
  id          bigserial   PRIMARY KEY,
  konusma_id  bigint      NOT NULL REFERENCES lcarlie.konusma(id) ON DELETE CASCADE,
  harici_id   text,                             -- Meta message id
  zaman       timestamptz NOT NULL,
  yon         text        NOT NULL,             -- gelen | giden
  gonderen    text        NOT NULL,             -- musteri | meta_ai | insan | ajan
  metin       text        NOT NULL DEFAULT '',
  ek          jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- medya, hızlı yanıt, reklam referansı
  -- değerlendirme (sonradan doldurulur)
  sinif       text,                             -- FIYAT | KARGO | BELIRTI_ANLATIMI ...
  mevzuat     text,                             -- TEMIZ | INCELE | BLOKLU
  bulgular    jsonb,
  olusturma   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS mesaj_harici_tekil
  ON lcarlie.mesaj (konusma_id, harici_id) WHERE harici_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS mesaj_konusma_zaman ON lcarlie.mesaj (konusma_id, zaman);
CREATE INDEX IF NOT EXISTS mesaj_gonderen      ON lcarlie.mesaj (gonderen, zaman DESC);
CREATE INDEX IF NOT EXISTS mesaj_mevzuat       ON lcarlie.mesaj (mevzuat) WHERE mevzuat IS NOT NULL;
-- Türkçe tam metin arama (benzer soru bulmak için)
CREATE INDEX IF NOT EXISTS mesaj_metin_fts
  ON lcarlie.mesaj USING gin (to_tsvector('simple', metin));

-- ---------------------------------------------------------------
-- HIZ (atomik hız sınırı — kanallar geri açılırsa kullanılacak)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lcarlie.hiz (
  kova        text        NOT NULL,
  pencere_bas timestamptz NOT NULL,
  sayac       integer     NOT NULL,
  ust         integer     NOT NULL,
  guncelleme  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kova, pencere_bas)
);

-- ---------------------------------------------------------------
-- mesaj_sayisi / son_mesaj otomatik güncellensin
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION lcarlie.konusma_tazele() RETURNS trigger AS $$
BEGIN
  UPDATE lcarlie.konusma k SET
    mesaj_sayisi = (SELECT count(*) FROM lcarlie.mesaj m WHERE m.konusma_id = k.id),
    ilk_mesaj    = (SELECT min(zaman) FROM lcarlie.mesaj m WHERE m.konusma_id = k.id),
    son_mesaj    = (SELECT max(zaman) FROM lcarlie.mesaj m WHERE m.konusma_id = k.id),
    guncelleme   = now()
  WHERE k.id = COALESCE(NEW.konusma_id, OLD.konusma_id);
  RETURN NULL;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS mesaj_sonrasi ON lcarlie.mesaj;
CREATE TRIGGER mesaj_sonrasi
  AFTER INSERT OR UPDATE OR DELETE ON lcarlie.mesaj
  FOR EACH ROW EXECUTE FUNCTION lcarlie.konusma_tazele();

-- ---------------------------------------------------------------
-- Kolay okuma görünümü
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW lcarlie.v_konusma_ozet AS
SELECT k.id, k.kanal, k.musteri_ad, k.musteri_ref, k.mesaj_sayisi,
       k.ilk_mesaj, k.son_mesaj, k.sonuc, k.siparis_no,
       (SELECT count(*) FROM lcarlie.mesaj m WHERE m.konusma_id=k.id AND m.gonderen='musteri') AS musteri_mesaji,
       (SELECT count(*) FROM lcarlie.mesaj m WHERE m.konusma_id=k.id AND m.gonderen='meta_ai') AS ai_mesaji,
       (SELECT count(*) FROM lcarlie.mesaj m WHERE m.konusma_id=k.id AND m.gonderen='insan')   AS insan_mesaji,
       (SELECT m.metin FROM lcarlie.mesaj m WHERE m.konusma_id=k.id AND m.gonderen='musteri'
         ORDER BY m.zaman LIMIT 1) AS ilk_soru
FROM lcarlie.konusma k;
