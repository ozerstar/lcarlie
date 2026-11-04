-- =============================================================================
-- L'CARLIE - AJANS / GROWTH KARAR KATMANI  (CR-014, Faz 1)
--
-- 🔴 BU KATMAN KARAR VERMEZ.  Insan icin KARAR BRIEF'i uretir.
--    Reklam butcesi degistirmez, kampanya durdurmaz/yayinlamaz, fiyat
--    degistirmez, sayfa yayinlamaz, iddia yayinlamaz. Yalniz okur ve yazar.
--
-- 🔴 AI/LLM KULLANILMIYOR - ve bu bir eksiklik degil, olcum sonucu:
--    sistemde hicbir LLM saglayicisi bagli degil (n8n'de 45 dugumun
--    0'i AI). Bu CR'nin tum cikarimlari DETERMINISTIK SQL kuralidir.
--    core.ai_calisma_log tablosu bos duruyor ve bos olmasi KANITTIR.
--    "AI yalniz deger urettigi yerde kullanilir" ilkesi: burada uretmiyor,
--    cunku girdi zaten sayisal ve kural netligi yorumdan degerli.
--
-- 🔴 KANIT DONDURULUR.  Her brief bir kanit anlik goruntusune baglidir.
--    Anlik goruntu olmadan bulgu uretilmez; boylece "o gun neye bakarak
--    bunu onerdik" sorusu sonradan cevaplanabilir.
-- =============================================================================

BEGIN;

-- ===========================================================================
-- TURKCE METIN NORMALIZASYONU
-- ===========================================================================
-- 🔴 NEDEN VAR - 16.09.2026'da olculdu:
--    PostgreSQL'de `~*` Turkce noktali I'yi kucuk i'ye ESLEMEZ:
--        'İçindekiler' ~* 'içindeki'   ->  FALSE
--    Bu yuzden bir analiz sorgusu 125 konusmayi 21 gosterdi (6 KAT EKSIK).
--    Ayrica veritabani collation'i en_US.utf8: NOKTASIZ ı hicbir yolla
--    eslesmiyor ('IŞIK' ILIKE '%ışık%' -> FALSE).
--
-- 🔴 KURAL: Turkce metin siniflandirmasinda `~*` ANA MEKANIZMA OLARAK
--    KULLANILMAZ. Hem mesaj hem kalip BU FONKSIYONDAN gecirilir.
--
-- 🔴 ORIJINAL MESAJ DEGISTIRILMEZ. lcarlie.mesaj.metin'e dokunulmaz;
--    normalizasyon yalniz ARAMA/SINIFLANDIRMA icin, sorgu aninda yapilir.
--
-- Esleme (translate, karakter karakter, deterministik):
--    İ I ı  -> i        (uc I de ayni harfe iner)
--    Ç ç    -> c
--    Ğ ğ    -> g
--    Ö ö    -> o
--    Ş ş    -> s
--    Ü ü    -> u
--    Â â Î î Û û -> a i u   (duzeltme isaretli harfler de duser)
--    kalan A-Z -> lower()
-- Sonuc: saf ASCII kucuk harf. 'İÇİNDEKİLER', 'ICINDEKILER', 'içindekiler'
--        hepsi 'icindekiler' olur.
CREATE OR REPLACE FUNCTION core.tr_norm(p text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT lower(translate(coalesce(p,''),
                         'İIıÇçĞğÖöŞşÜüÂâÎîÛû',
                         'iiiccggoossuuaaiiuu'));
$$;

COMMENT ON FUNCTION core.tr_norm(text) IS
  'Turkce metni arama/siniflandirma icin saf ASCII kucuk harfe indirger. '
  'Orijinal metni DEGISTIRMEZ. ~* yerine bu kullanilir.';

-- ---------------------------------------------------------------------------
-- PII MASKELEME  -  ornek mesajlar rapora/brief''e girmeden once
-- ---------------------------------------------------------------------------
-- 🔴 Musteri mesaji SERBEST METINDIR: telefon, e-posta, ad icerebilir.
--    Ornek mesaj gostermek analiz icin degerli ama PII tasimak yasak
--    (CR-002.5: "PII loglara yazilmaz", "raw PII erisimi minimum").
--    Bu fonksiyon rakam dizisi, e-posta ve @kullanici adlarini maskeler.
CREATE OR REPLACE FUNCTION core.pii_maskele(p text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT regexp_replace(
           regexp_replace(
             regexp_replace(coalesce(p,''),
               '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}', '[eposta]', 'g'),
             '@[[:alnum:]._]{3,}', '[kullanici]', 'g'),
           '[0-9][0-9 ()+-]{6,}[0-9]', '[numara]', 'g');
$$;

COMMENT ON FUNCTION core.pii_maskele(text) IS
  'Ornek mesajlardan telefon/e-posta/kullanici adi maskeler. Brief''e ham mesaj GIRMEZ.';

-- ---------------------------------------------------------------------------
-- KANIT ANLIK GORUNTUSU
-- ---------------------------------------------------------------------------
-- 🔴 APPEND-ONLY. Guncellenmez. Gecmis kaniti degistirmek, gecmiste ne
--    bildigimizi yok etmek olur (CR-012'de ayni gerekceyle rapor_anlik).
CREATE TABLE IF NOT EXISTS core.kanit_anlik (
  anlik_id     bigserial PRIMARY KEY,
  alindi       timestamptz NOT NULL DEFAULT clock_timestamp(),
  surum        text        NOT NULL,          -- kanit sozlesmesi surumu
  pencere_7    jsonb       NOT NULL,
  pencere_30   jsonb       NOT NULL,
  urun         jsonb       NOT NULL,
  kanal        jsonb       NOT NULL,
  konusma      jsonb       NOT NULL,
  veri_kalitesi jsonb      NOT NULL,
  eksik_kaynak jsonb       NOT NULL,
  kanit_puani  int         NOT NULL,
  kanit_sinifi text        NOT NULL           -- LOW | MEDIUM | HIGH
);
COMMENT ON TABLE core.kanit_anlik IS
  'Her brief''in dayandigi dondurulmus kanit. ASLA guncellenmez.';

-- ---------------------------------------------------------------------------
-- BULGULAR  (modul ciktilari)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.buyume_bulgu (
  bulgu_id     bigserial PRIMARY KEY,
  anlik_id     bigint NOT NULL REFERENCES core.kanit_anlik(anlik_id) ON DELETE CASCADE,
  modul        text   NOT NULL,   -- META | URUN | KREATIF | CRO | PAZAR | RED_TEAM
  -- 🔴 KANIT SEVIYESI HER BULGUDA ZORUNLU. "Gozlendi" ile "varsayildi"
  --    ayni satirda gorunmezse okuyan ikisini karistirir.
  seviye       text   NOT NULL CHECK (seviye IN ('OBSERVED','INFERRED','HYPOTHESIS','NOT_CONNECTED')),
  sinif        text,              -- SCALE_CANDIDATE | TEST_SMALL | HOLD | FIX_FUNNEL_FIRST | INSUFFICIENT_DATA
                                  -- RED_TEAM icin: SUPPORT | CHALLENGE | INSUFFICIENT_EVIDENCE
  baslik       text   NOT NULL,
  kanit        text   NOT NULL,   -- hangi sayi/kaynak
  beklenen_etki text,
  risk         text,
  kanit_sinifi text,              -- LOW | MEDIUM | HIGH
  yanlislama   text,              -- bu oneriyi NE CURUTUR
  insan_onayi  boolean NOT NULL DEFAULT true,
  olusturma    timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS buyume_bulgu_anlik_idx ON core.buyume_bulgu (anlik_id, modul);
COMMENT ON TABLE core.buyume_bulgu IS
  'Modul ciktilari. Her satir kanit seviyesi ve yanlislama kosulu tasir.';

-- ---------------------------------------------------------------------------
-- KARAR KAYDI  -  CR-015 SOZLESMESI (bu CR''de OTOMATIK DOLDURULMAZ)
-- ---------------------------------------------------------------------------
-- 🔴 Tablo simdi kuruluyor ki CR-015 semayi degistirmek zorunda kalmasin.
--    Ama outcome learning BASLATILMIYOR: actual_result ve outcome_status
--    yalnizca INSAN tarafindan doldurulur.
CREATE TABLE IF NOT EXISTS core.karar_kaydi (
  karar_id          bigserial PRIMARY KEY,
  tarih             date        NOT NULL DEFAULT (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date,
  oneri             text        NOT NULL,
  anlik_id          bigint      REFERENCES core.kanit_anlik(anlik_id),
  beklenen_etki     text,
  kanit_kalitesi    text,
  red_team_sonucu   text,
  insan_karari      text,       -- ONAY | RED | ERTELE  (insan girer)
  uygulanan_aksiyon text,
  gercek_sonuc      text,
  sonuc_durumu      text CHECK (sonuc_durumu IN ('DOGRU','YANLIS','BELIRSIZ') OR sonuc_durumu IS NULL),
  yanlislama_kosulu text,
  olusturma         timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE core.karar_kaydi IS
  'CR-015 Decision Memory sozlesmesi. CR-014''te OTOMATIK DOLDURULMAZ - insan girer.';

-- ---------------------------------------------------------------------------
-- AI CALISMA LOGU
-- ---------------------------------------------------------------------------
-- 🔴 BOS OLMASI KANITTIR: bu CR'de hicbir LLM cagrisi yapilmadi.
--    Ileride AI eklenirse her cagri buraya yazilmak ZORUNDA - maliyeti
--    gorunmeyen bir agent, emekliye ayrilamayan bir agenttir.
CREATE TABLE IF NOT EXISTS core.ai_calisma_log (
  calisma_id  bigserial PRIMARY KEY,
  zaman       timestamptz NOT NULL DEFAULT clock_timestamp(),
  saglayici   text NOT NULL,
  model       text NOT NULL,
  gorev       text NOT NULL,
  anlik_id    bigint REFERENCES core.kanit_anlik(anlik_id),
  girdi_token int,
  cikti_token int,
  maliyet_usd numeric(12,6),
  sonuc       text
);
COMMENT ON TABLE core.ai_calisma_log IS
  'Her LLM cagrisi buraya yazilir. BOS = hic AI kullanilmadi.';

COMMIT;
