-- =============================================================================
-- L'CARLIE - RAW CIKARMA FONKSIYONLARI  (CR-004 Faz 1)
--
-- 🔴 NEDEN AYRI FONKSIYON?
--    Cikarma kurallari ETL betiginin ICINDE olursa, bir kural yanlis ciktiginda
--    veriyi kaynaktan YENIDEN CEKMEK gerekir. Burada oldugu gibi ayri olunca:
--        SELECT raw.wix_order_yaz(ham) FROM raw.wix_order;
--    demek yeter - ham veri zaten elimizde, kaynaga hic dokunulmaz.
--
-- 🔴 HER FONKSIYON IDEMPOTENT: ayni JSON iki kez verilirse ikinci sefer
--    'UPDATE' doner, ikinci satir OLUSMAZ.
--
-- 🔴 PII: BasitKargo alici adi/telefonu/adresi ham jsonb'ye de YAZILMAZ.
--    Temizleme fonksiyonun ICINDE yapilir ki ham kolon bile temiz kalsin.
-- =============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Yardimcilar
-- --------------------------------------------------------------------------

-- Bos string -> NULL.  ''::numeric hata verir, ''::timestamptz hata verir.
CREATE OR REPLACE FUNCTION raw.bos_null(t text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$ SELECT nullif(btrim(coalesce(t,'')),'') $$;

CREATE OR REPLACE FUNCTION raw.sayi(t text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF raw.bos_null(t) IS NULL THEN RETURN NULL; END IF;
  RETURN t::numeric;
EXCEPTION WHEN others THEN
  -- 🔴 Sessizce 0 DONDURME. Cozulemeyen sayi = NULL = "bilmiyoruz".
  RETURN NULL;
END $$;

-- Offset'siz BasitKargo tarihi -> timestamptz (+03 varsayimi, semada belgelendi)
-- 🔴 STABLE, IMMUTABLE DEGIL: text->timestamptz cast'i oturumun TimeZone
--    ayarina baglidir. IMMUTABLE isaretlemek indeks kullanildiginda yanlis
--    sonuc uretir.
CREATE OR REPLACE FUNCTION raw.bk_zaman(t text) RETURNS timestamptz
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF raw.bos_null(t) IS NULL THEN RETURN NULL; END IF;
  IF t ~ '(Z|[+-]\d{2}:?\d{2})$' THEN RETURN t::timestamptz; END IF;
  RETURN (t || '+03')::timestamptz;
EXCEPTION WHEN others THEN
  RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION raw.zaman(t text) RETURNS timestamptz
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF raw.bos_null(t) IS NULL THEN RETURN NULL; END IF;
  RETURN t::timestamptz;
EXCEPTION WHEN others THEN
  RETURN NULL;
END $$;

-- --------------------------------------------------------------------------
-- BasitKargo: alici PII'sini ham JSON'dan CIKAR
-- --------------------------------------------------------------------------
-- Tutulan: recipient.city, recipient.town  (bolgesel dagilim icin)
-- Atilan : recipient.name / phone / address  ve sender.phone
CREATE OR REPLACE FUNCTION raw.bk_pii_temizle(j jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_set(
           jsonb_set(j, '{recipient}',
             jsonb_strip_nulls(jsonb_build_object(
               'city', j#>'{recipient,city}',
               'town', j#>'{recipient,town}',
               'pii_temizlendi', to_jsonb(true)))),
           '{sender}',
           jsonb_strip_nulls(jsonb_build_object('name', j#>'{sender,name}')))
$$;

-- --------------------------------------------------------------------------
-- WIX SIPARIS
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION raw.wix_order_yaz(j jsonb)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_id text; v_yeni boolean;
BEGIN
  v_id := raw.bos_null(j->>'id');
  IF v_id IS NULL THEN
    -- Ayni gerekce: Wix PII'si kimlik icin saklaniyor ama yukleme gunlugu
    -- AYRI bir maruziyet yuzeyidir; oraya alici bilgisi dusmemeli.
    RAISE EXCEPTION 'Wix siparisinde id yok (no=%, tarih=%)',
      coalesce(j->>'number','?'), coalesce(j->>'dateCreated','?');
  END IF;

  INSERT INTO raw.wix_order AS w (
    siparis_id, siparis_no, buyer_id, buyer_tipi, olusturma, guncelleme,
    odeme_durumu, odeme_yontemi, teslimat_durumu, toplam, para_birimi,
    kanal, arsivlendi, giren_id, giren_tipi, ic_siparis,
    ara_toplam, kdv, kargo_bedeli, siparis_indirimi, ham, cekim_at)
  VALUES (
    v_id,
    raw.sayi(j->>'number')::bigint,
    raw.bos_null(j#>>'{buyerInfo,id}'),
    raw.bos_null(j#>>'{buyerInfo,identityType}'),
    raw.zaman(j->>'dateCreated'),
    raw.zaman(j->>'lastUpdated'),
    raw.bos_null(j->>'paymentStatus'),
    raw.bos_null(j#>>'{billingInfo,paymentMethod}'),
    raw.bos_null(j->>'fulfillmentStatus'),
    raw.sayi(j#>>'{totals,total}'),
    raw.bos_null(j->>'currency'),
    raw.bos_null(j#>>'{channelInfo,type}'),
    -- 🔴 Wix bu alanlari "False"/"True" METNI olarak dondurur, boolean degil.
    lower(coalesce(j->>'archived','')) IN ('true','t'),
    raw.bos_null(j#>>'{enteredBy,id}'),
    raw.bos_null(j#>>'{enteredBy,identityType}'),
    lower(coalesce(j->>'isInternalOrderCreate','')) IN ('true','t'),
    -- 🔴 KDV AYRI OKUNUR (CR-012). totals.total KDV DAHILDIR; marj hesabi
    --    icin KDV haric taban gerekir. Alan yoksa NULL kalir - 0 YAZILMAZ,
    --    cunku "KDV yok" ile "KDV bilinmiyor" ayni sey degildir ve 0 yazmak
    --    KDV dahil tutari KDV haric gibi gosterirdi.
    -- 🔴 NET CIRO = toplam - kdv.  ara_toplam (subtotal) KULLANILMAZ:
    --    o indirim ONCESI liste tutaridir, matrah degildir.
    raw.sayi(j#>>'{totals,subtotal}'),
    raw.sayi(j#>>'{totals,tax}'),
    raw.sayi(j#>>'{totals,shipping}'),
    raw.sayi(j#>>'{totals,discount}'),
    j, now())
  ON CONFLICT (siparis_id) DO UPDATE SET
    siparis_no      = EXCLUDED.siparis_no,
    buyer_id        = EXCLUDED.buyer_id,
    buyer_tipi      = EXCLUDED.buyer_tipi,
    olusturma       = EXCLUDED.olusturma,
    guncelleme      = EXCLUDED.guncelleme,
    odeme_durumu    = EXCLUDED.odeme_durumu,
    odeme_yontemi   = EXCLUDED.odeme_yontemi,
    teslimat_durumu = EXCLUDED.teslimat_durumu,
    toplam          = EXCLUDED.toplam,
    para_birimi     = EXCLUDED.para_birimi,
    kanal           = EXCLUDED.kanal,
    arsivlendi      = EXCLUDED.arsivlendi,
    giren_id        = EXCLUDED.giren_id,
    giren_tipi      = EXCLUDED.giren_tipi,
    ic_siparis      = EXCLUDED.ic_siparis,
    ara_toplam      = EXCLUDED.ara_toplam,
    kdv             = EXCLUDED.kdv,
    kargo_bedeli    = EXCLUDED.kargo_bedeli,
    siparis_indirimi= EXCLUDED.siparis_indirimi,
    ham             = EXCLUDED.ham,
    cekim_at        = EXCLUDED.cekim_at
  RETURNING (w.xmax = 0) INTO v_yeni;

  -- Kalemler: siparisin kalem listesi kaynakta degisebilir (iptal/duzeltme).
  -- 🔴 Once sil sonra yaz - aksi halde SILINEN kalem sonsuza dek kalir.
  DELETE FROM raw.wix_order_item WHERE siparis_id = v_id;
  INSERT INTO raw.wix_order_item (siparis_id, sira, urun_id, urun_adi, sku, adet,
                                  birim_fiyat, toplam, indirim, ham)
  SELECT v_id,
         coalesce(raw.sayi(it->>'index')::int, ord::int),
         raw.bos_null(it->>'productId'),
         raw.bos_null(it->>'name'),
         raw.bos_null(it->>'sku'),
         raw.sayi(it->>'quantity'),
         raw.sayi(it->>'price'),
         raw.sayi(it->>'totalPrice'),
         -- 🔴 Kalem indirimi DUZ METINDIR: "1680.00". 'discount.amount' diye
         --    bir alt alan YOKTUR - oraya bakan kod indirimi hep 0 gorur.
         --    Bu alan okunmadigi icin ciro %18,8 sisik hesaplaniyordu.
         coalesce(raw.sayi(it->>'discount'), 0),
         it
    FROM jsonb_array_elements(coalesce(j->'lineItems','[]'::jsonb))
         WITH ORDINALITY AS t(it, ord);

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;

-- --------------------------------------------------------------------------
-- BASITKARGO GONDERI
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION raw.bk_shipment_yaz(j_ham jsonb)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_id text; v_yeni boolean; j jsonb;
BEGIN
  v_id := raw.bos_null(j_ham->>'id');
  IF v_id IS NULL THEN
    -- 🔴 HATA MESAJINA HAM GOVDE YAZILMAZ (16.09 denetimi).
    --    Onceki hali left(j_ham::text,200) yaziyordu - yani PII TEMIZLENMEDEN
    --    ONCEKI hali. Bu metin psql stderr'ine, oradan ETL ciktisina, oradan
    --    raw.yukleme_log.mesaj'a dusuyordu. Yani "ham jsonb'de bile tutulmaz"
    --    denen alici adi/telefonu/adresi, LOG TABLOSUNA sizabiliyordu.
    --    Teshis icin PII olmayan alanlar yeterli.
    RAISE EXCEPTION 'BasitKargo gonderisinde id yok (barkod=%, tarih=%)',
      coalesce(j_ham->>'barcode','?'), coalesce(j_ham->>'createdTime','?');
  END IF;
  j := raw.bk_pii_temizle(j_ham);   -- 🔴 ham kolona da temizlenmis hali girer

  INSERT INTO raw.bk_shipment AS b (
    gonderi_id, barkod, foreign_code, icerik_kodu, ek_bilgi, yon, gonderi_no,
    durum, tasiyici, olusturma, guncelleme, kargoya_verilis, teslim, son_hareket,
    desi, kargo_ucreti, toplam_maliyet, cod_var, cod_tutar, cod_durum,
    siparis_tutari, urun_adlari, sehir, ilce, ham, cekim_at)
  VALUES (
    v_id,
    raw.bos_null(j->>'barcode'),
    raw.bos_null(j->>'foreignCode'),
    raw.bos_null(j#>>'{content,code}'),
    raw.bos_null(j#>>'{content,name}'),
    raw.bos_null(j->>'type'),
    raw.bos_null(j->>'orderNumber'),
    raw.bos_null(j->>'status'),
    raw.bos_null(j#>>'{shipmentInfo,handler,name}'),
    raw.bk_zaman(j->>'createdTime'),
    raw.bk_zaman(j->>'updatedTime'),
    raw.bk_zaman(j#>>'{shipmentInfo,shippedTime}'),
    raw.bk_zaman(j#>>'{shipmentInfo,deliveredTime}'),
    raw.bos_null(j#>>'{shipmentInfo,lastState}'),
    coalesce(raw.sayi(j#>>'{shipmentInfo,handlerDesi}'), raw.sayi(j#>>'{content,totalDesiKg}')),
    raw.sayi(j#>>'{priceInfo,shipmentFee}'),
    raw.sayi(j#>>'{priceInfo,totalCost}'),
    coalesce((j#>>'{codInfo,collectOnDelivery}')::boolean, false),
    raw.sayi(j#>>'{codInfo,amount}'),
    raw.bos_null(j#>>'{codInfo,collectionStatus}'),
    raw.sayi(j->>'orderTotal'),
    (SELECT array_agg(raw.bos_null(it->>'name') ORDER BY ord)
       FROM jsonb_array_elements(coalesce(j#>'{content,items}','[]'::jsonb))
            WITH ORDINALITY AS t(it, ord)
      WHERE raw.bos_null(it->>'name') IS NOT NULL),
    raw.bos_null(j#>>'{recipient,city}'),
    raw.bos_null(j#>>'{recipient,town}'),
    j, now())
  ON CONFLICT (gonderi_id) DO UPDATE SET
    barkod          = EXCLUDED.barkod,
    foreign_code    = EXCLUDED.foreign_code,
    icerik_kodu     = EXCLUDED.icerik_kodu,
    ek_bilgi        = EXCLUDED.ek_bilgi,
    yon             = EXCLUDED.yon,
    gonderi_no      = EXCLUDED.gonderi_no,
    durum           = EXCLUDED.durum,
    tasiyici        = EXCLUDED.tasiyici,
    olusturma       = EXCLUDED.olusturma,
    guncelleme      = EXCLUDED.guncelleme,
    kargoya_verilis = EXCLUDED.kargoya_verilis,
    teslim          = EXCLUDED.teslim,
    son_hareket     = EXCLUDED.son_hareket,
    desi            = EXCLUDED.desi,
    kargo_ucreti    = EXCLUDED.kargo_ucreti,
    toplam_maliyet  = EXCLUDED.toplam_maliyet,
    cod_var         = EXCLUDED.cod_var,
    cod_tutar       = EXCLUDED.cod_tutar,
    cod_durum       = EXCLUDED.cod_durum,
    siparis_tutari  = EXCLUDED.siparis_tutari,
    urun_adlari     = EXCLUDED.urun_adlari,
    sehir           = EXCLUDED.sehir,
    ilce            = EXCLUDED.ilce,
    ham             = EXCLUDED.ham,
    cekim_at        = EXCLUDED.cekim_at
  RETURNING (b.xmax = 0) INTO v_yeni;

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;

COMMIT;
