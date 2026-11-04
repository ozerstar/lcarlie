-- =============================================================================
-- L'CARLIE - DECISION MEMORY TEST SENARYOLARI  (CR-015)
--
-- 🔴 HEPSI fixture=true VE 'test-' onekli.  Uretim gorunumleri (mart.karar_ozet,
--    mart.karar_son, mart.karar_kalibrasyon) bunlari DISLAR - CR-002.5'te
--    kurulan "test verisi uretime karismaz" kurali burada da gecerli.
--
-- 🔴 Idempotent: tekrar calistirildiginda duplicate URETMEZ (idempotency_key).
-- =============================================================================

BEGIN;

-- Onceki fixture'lari temizle (YALNIZ fixture; uretim kararina dokunulmaz)
DELETE FROM core.karar WHERE fixture;

DO $$
DECLARE v_anlik bigint; v_a bigint; v_b bigint; v_c bigint; v_d bigint;
BEGIN
  SELECT max(anlik_id) INTO v_anlik FROM core.kanit_anlik;

  -- ---------------------------------------------------------------------
  -- A) ONAY -> AKSIYON -> OLCULEBILIR SONUC
  -- ---------------------------------------------------------------------
  INSERT INTO core.karar (karar_tipi, urun, oneri, anlik_id, kanit_kalitesi,
                          beklenen_etki, risk, yanlislama_kosulu, idempotency_key, fixture)
  VALUES ('CRO_CHANGE','test-urun','test-A: urun sayfasina icerik listesi eklensin',
          v_anlik,'MEDIUM','icerik sorusu azalir','konusma dususu yanlis okunabilir',
          'Icerik one alindiktan sonra ayni soru orani DUSMEZSE hipotez curur',
          'fixture-A', true) RETURNING karar_id INTO v_a;
  INSERT INTO core.karar_red_team (karar_id, sonuc, itiraz_tipi, gerekce, kanit_referansi)
  VALUES (v_a,'SUPPORT','ORNEKLEM','test: kanit yeterli','fixture');
  INSERT INTO core.karar_insan (karar_id, karar, karar_notu, onaylayan)
  VALUES (v_a,'APPROVE','test onayi','test-kullanici');
  UPDATE core.karar SET durum='APPROVED' WHERE karar_id=v_a;
  -- 🔴 Aksiyon 30 gun ONCE uygulanmis gibi: olcum penceresi acilsin.
  INSERT INTO core.karar_aksiyon (karar_id, aksiyon_tipi, aciklama, uygulandi, uygulayan,
                                  onceki_durum, sonraki_durum)
  VALUES (v_a,'landing_page_changed','test-A aksiyonu',
          clock_timestamp()-interval '30 days','test-kullanici','icerik yok','icerik var');
  UPDATE core.karar SET durum='EXECUTED' WHERE karar_id=v_a;

  -- ---------------------------------------------------------------------
  -- B) RED -> AKSIYON YOK
  -- ---------------------------------------------------------------------
  INSERT INTO core.karar (karar_tipi, oneri, anlik_id, kanit_kalitesi, yanlislama_kosulu,
                          idempotency_key, fixture)
  VALUES ('MEDIA_BUDGET','test-B: reklam butcesi artirilsin', v_anlik,'LOW',
          'Butce artisindan sonra siparis artmazsa oneri curur','fixture-B', true)
  RETURNING karar_id INTO v_b;
  INSERT INTO core.karar_red_team (karar_id, sonuc, itiraz_tipi, gerekce, kanit_referansi)
  VALUES (v_b,'CHALLENGE','FINANSAL','test: nakit durumu CRITICAL','fixture');
  INSERT INTO core.karar_insan (karar_id, karar, karar_notu, onaylayan)
  VALUES (v_b,'REJECT','test reddi - once huni','test-kullanici');
  UPDATE core.karar SET durum='REJECTED' WHERE karar_id=v_b;

  -- ---------------------------------------------------------------------
  -- C) ONAY -> AKSIYON -> ORNEKLEM YETERSIZ -> INCONCLUSIVE
  -- ---------------------------------------------------------------------
  INSERT INTO core.karar (karar_tipi, oneri, anlik_id, kanit_kalitesi, yanlislama_kosulu,
                          idempotency_key, fixture)
  VALUES ('OFFER_TEST','test-C: yeni teklif denensin', v_anlik,'LOW',
          'Teklif sonrasi donusum artmazsa oneri curur','fixture-C', true)
  RETURNING karar_id INTO v_c;
  INSERT INTO core.karar_insan (karar_id, karar, karar_notu, onaylayan)
  VALUES (v_c,'APPROVE','test onayi','test-kullanici');
  UPDATE core.karar SET durum='APPROVED' WHERE karar_id=v_c;
  -- 🔴 Aksiyon 10 gun once: pencere yeterli AMA orneklem (siparis) yetersiz.
  INSERT INTO core.karar_aksiyon (karar_id, aksiyon_tipi, aciklama, uygulandi, uygulayan)
  VALUES (v_c,'offer_changed','test-C aksiyonu',
          clock_timestamp()-interval '10 days','test-kullanici');
  UPDATE core.karar SET durum='EXECUTED' WHERE karar_id=v_c;

  -- ---------------------------------------------------------------------
  -- D) RED TEAM CHALLENGE -> INSAN DEFER
  -- ---------------------------------------------------------------------
  INSERT INTO core.karar (karar_tipi, oneri, anlik_id, kanit_kalitesi, yanlislama_kosulu,
                          idempotency_key, fixture)
  VALUES ('CREATIVE_TEST','test-D: yeni kreatif yayinlansin', v_anlik,'LOW',
          'Kreatif sonrasi mesaj basina maliyet dusmezse oneri curur','fixture-D', true)
  RETURNING karar_id INTO v_d;
  INSERT INTO core.karar_red_team (karar_id, sonuc, itiraz_tipi, gerekce, kanit_referansi)
  VALUES (v_d,'CHALLENGE','MEVZUAT','test: mevzuat kapisindan gecmedi','fixture'),
         (v_d,'CHALLENGE','KAPSAMA','test: kreatif verisi yok','fixture');
  INSERT INTO core.karar_insan (karar_id, karar, karar_notu, onaylayan)
  VALUES (v_d,'DEFER','test erteleme - once mevzuat','test-kullanici');
  UPDATE core.karar SET durum='DEFERRED' WHERE karar_id=v_d;

  -- Sonuclari kapat (A ve C)
  PERFORM core.karar_sonuclandir(v_a,'test-siparis', 5, 9, 'test-kullanici');
  PERFORM core.karar_sonuclandir(v_c,'test-donusum', 2, 3, 'test-kullanici');
END $$;

COMMIT;
