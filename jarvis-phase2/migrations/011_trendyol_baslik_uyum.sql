-- 011 — TRENDYOL BAŞLIK UYUM BULGULARI onay kutusuna
--
-- BULGU
-- Trendyol'daki 34 L'CARLIÉ ürününün 4'ünün BAŞLIĞI, şirketin kendi yazım
-- kılavuzunun yasak listesinden ifade taşıyor. Aynı düzeltmeler Wix'te
-- yapılmış, Trendyol'a uygulanmamış.
--
-- NEDEN YENİ İŞLEM TİPİ EKLENMEDİ
-- İlk tasarım MARKETPLACE_CONTENT_CHANGE diye yeni bir tip eklemekti.
-- Kuru çalıştırma gösterdi ki yetmez: core.ai_propose_action her tip için
-- payload şemasını kendi CASE'inde doğruluyor ve tanımadığını reddediyor.
-- Yani tabloya satır ekleyerek yeni bir dış işlem tipi kaçırılamıyor --
-- kasıtlı bir güvenlik tasarımı. O fonksiyon eylem güvenlik duvarının
-- kendisidir; bu migration ONU DEĞİŞTİRMEZ.
--
-- Bunun yerine REQUEST_HUMAN_REVIEW kullanılır: tasarımın "bir insan buna
-- baksın" için ayırdığı yol.
--
-- BİR GÖREV = BİR ÖNERİ
-- İlk denemede üç öneriyi tek görevden yazmaya çalıştım; ikincisi
-- 'invalid action task' ile düştü. Sebep ölçüldü: öneri yazmak görevin
-- durumunu değiştiriyor, görev artık LEASED değil. Bu yüzden her öneri
-- KENDİ görevinden doğar.
--
-- SOFTGUARD DIŞARIDA
-- SOFTGUARD'ın "Akar Önleyici" başlığı da listede ama işletme sahibi o
-- konuyu kapattı. Bulgu raporlanır, öneri ÜRETİLMEZ.
--
-- ÖNERİLEN ADLAR UYDURULMADI
-- Üçü de Wix'te ZATEN ONAYLANMIŞ adlardır; iki platform tutarlı olur.

\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
  v_oneri  record;
  v_task   bigint;
  v_kayit  record;
  v_sayac  int := 0;
BEGIN
  FOR v_oneri IN
    SELECT * FROM (VALUES
      ('8684869609271',
       'DERMAVASC: basliktaki "Onarici" tedavi dilidir (kilavuz §2). '
       || 'SIMDI: "DERMAVASC (Onarici Bakim Kremi)" -> '
       || 'ONERI: "DERMAVASC (Bacak ve Vucut Bakim Kremi)". '
       || 'Onerilen ad Wix''te zaten onayli; iki platform tutarli olur.'),
      ('8684869609561',
       'DERMASTRA: basliktaki "Elastikiyeti" fizyolojik etki iddiasidir '
       || '(kilavuz §2). SIMDI: "DERMASTRA (Cilt Elastikiyeti Destekleyici '
       || 'Bitkisel Bakim Kremi)" -> ONERI: "DERMASTRA (Gerilme Bolgeleri '
       || 'Icin Bitkisel Bakim Kremi)". Onerilen ad Wix''te zaten onayli.'),
      ('8684869609325',
       'MINISOOTH: basliktaki "Onleyici" sonuc vaadidir, ayrica "Pisik" '
       || 'lezyon adidir (kilavuz §2). SIMDI: "BABYLINE MINISOOTH Bebek '
       || 'Pisik Onleyici Bakim Kremi 100 ml - Cinko Oksit ve 13 Bitkisel '
       || 'Bilesen" -> ONERI: ayni baslik, "Pisik Onleyici" yerine '
       || '"Bez Bolgesi". Wix''teki onayli adla uyumlu.')
    ) AS t(barkod, gerekce)
  LOOP
    -- Her oneri KENDI gorevinden dogar.
    v_task := core.ai_enqueue_task(
      p_source_type     => 'MANUAL',
      p_source_id       => NULL,
      p_task_type       => 'PROPOSE_ACTION',
      p_idempotency_key => 'ty-baslik-uyum-' || v_oneri.barkod || '-20260920',
      p_priority        => 10,
      p_enqueue_reason  => 'Trendyol baslik uyumu: ' || v_oneri.barkod);

    SELECT * INTO v_kayit FROM core.ai_claim_task('jarvis:compliance', 600);
    IF v_kayit IS NULL OR v_kayit.task_id IS DISTINCT FROM v_task THEN
      -- Claim hangi gorevi alacagini SECTIRMEZ. Baska bir gorev geldiyse
      -- devam etmek yanlis goreve oneri yazmak olurdu.
      RAISE EXCEPTION 'claim beklenen gorevi (%) degil, %''i dondurdu',
        v_task, coalesce(v_kayit.task_id, -1);
    END IF;

    PERFORM core.ai_propose_action(
      p_task_id         => v_task,
      p_lease_token     => v_kayit.lease_token,
      -- Anahtar 'action:' ile BASLAMAK ZORUNDA.
      p_idempotency_key => 'action:ty-baslik-' || v_oneri.barkod || '-20260920',
      p_action_type     => 'REQUEST_HUMAN_REVIEW',
      -- Payload SADECE subject_ref + reason; fazladan anahtar reddedilir.
      p_payload         => jsonb_build_object(
        'subject_ref', 'trendyol:' || v_oneri.barkod,
        'reason',      v_oneri.gerekce));

    v_sayac := v_sayac + 1;
    RAISE NOTICE 'oneri % -> gorev %, barkod %', v_sayac, v_task, v_oneri.barkod;
  END LOOP;

  RAISE NOTICE 'toplam % oneri olusturuldu', v_sayac;
END $$;

COMMIT;
