-- =============================================================================
-- L'CARLIE - ILK GERCEK INSAN KARARI  (Chief Architect, 16.09.2026)
--
-- 🔴 BU BIR TEST DEGIL.  fixture=false, uretim kaydi.
-- 🔴 HICBIR REKLAM DEGISTIRILMEDI. Karar "butceyi buyutme" karari;
--    "tum reklamlari kapat" DEGIL. Aksiyon tipi bu yuzden no_action:
--    mevcut harcama oldugu gibi korunuyor, artis YAPILMADI.
-- =============================================================================

BEGIN;

DO $$
DECLARE r record; v_not text; v_yanlis text;
BEGIN
  v_not := 'Chief Architect karari 16.09.2026: MODIFY. '
        || 'Paid media SCALE YOK · yeni butce artisi YOK · yeni genisleme YOK. '
        || 'Mevcut reklam harcamasi KONTROLLU KORUNACAK. '
        || 'Meta ads_read + diger iki hesabin gorunurlugu cozulmeden scale karari verilmeyecek. '
        || 'Cash Guardrail CRITICAL kaldigi surece butce artisi insan onayi olmadan mumkun degil. '
        || 'GEREKCE: gozlenen paid spend, olculen gelir tabanina gore zayif ekonomi gosteriyor; '
        || 'kanit kalitesi LOW ve Meta kapsamasi yalniz 1/3.';

  v_yanlis := 'Eksik Meta hesaplari + dogrulanmis gelir (PayTR/muhasebe) + gercek COGS + '
           || 'payment authority geldikten SONRA paid media ekonomisi POZITIF ve '
           || 'TEKRARLANABILIR gorunurse bu karar yeniden degerlendirilir. '
           || 'Ayrica: olculmeyen gelir (Wix disi kapida odeme, WhatsApp/telefon satisi) '
           || 'sisteme girdiginde gelir tabani yukselirse ekonomi degisebilir.';

  -- 🔴 Karar HER IKI MEDIA_BUDGET adayina uygulanir: ikisi de ayni ticari
  --    olguyu (7 ve 30 gunluk CRITICAL) tarif ediyor ve tek kararla kapaniyor.
  FOR r IN SELECT karar_id FROM core.karar
            WHERE NOT fixture AND karar_tipi='MEDIA_BUDGET'
              AND durum IN ('PROPOSED','DEFERRED') ORDER BY karar_id
  LOOP
    -- Yanlislama kosulunu Chief Architect'in verdigi metinle guncelle
    UPDATE core.karar SET yanlislama_kosulu = v_yanlis WHERE karar_id = r.karar_id;

    INSERT INTO core.karar_insan (karar_id, karar, karar_notu, onaylayan)
    VALUES (r.karar_id, 'MODIFY', v_not, 'Chief Architect')
    ON CONFLICT (karar_id) DO UPDATE
      SET karar=EXCLUDED.karar, karar_notu=EXCLUDED.karar_notu,
          onaylayan=EXCLUDED.onaylayan, karar_zamani=clock_timestamp();

    UPDATE core.karar SET durum='APPROVED' WHERE karar_id=r.karar_id;

    -- 🔴 AKSIYON: no_action. "Hicbir sey yapilmadi" DEGIL - "butce
    --    artirilmadi, mevcut harcama korundu" KARARI uygulandi.
    --    Bu bir aksiyondur ve kayda gecer; yoksa sonradan "karar verildi
    --    ama ne yapildi" sorusu cevapsiz kalir.
    INSERT INTO core.karar_aksiyon (karar_id, aksiyon_tipi, aciklama, uygulayan,
                                    onceki_durum, sonraki_durum)
    VALUES (r.karar_id, 'no_action',
            'Butce artisi YAPILMADI. Mevcut Meta harcamasi oldugu gibi korundu. '
            'Kampanya durdurulmadi, yeni kampanya acilmadi, fiyat degistirilmedi.',
            'Chief Architect',
            'mevcut harcama seviyesi', 'mevcut harcama seviyesi (degismedi)');

    UPDATE core.karar SET durum='EXECUTED'  WHERE karar_id=r.karar_id;
    -- 🔴 MEASURING: karar uygulandi, sonuc penceresi acik ama HENUZ
    --    olculebilir degil (orneklem<10). Sonuc satiri YAZILMIYOR -
    --    zorla INCONCLUSIVE uretmek yerine durum MEASURING'de bekliyor.
    UPDATE core.karar SET durum='MEASURING' WHERE karar_id=r.karar_id;
  END LOOP;
END $$;

COMMIT;
