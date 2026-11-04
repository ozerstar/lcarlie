-- Authorised HR agent team. Existing departments are not changed.
BEGIN;
INSERT INTO core.departman
    (kod, ad, aile, misyon, durum, veri_kaynagi, otonomi_tavani, escalation)
VALUES ('HR', 'İnsan Kaynakları ve Organizasyon', 'INSAN_VE_ORGANIZASYON',
        'Ajan kadrosunu, sorumlulukları, kaynak eksiklerini ve açık iş kayıtlarını kanıta dayalı denetler.',
        'KISMI', 'core.departman; şirket açık iş, gündem, öneri ve öğrenme kayıtları',
        'L1', 'Genel müdür; kadro ve yetki değişiklikleri için sahip onayı')
ON CONFLICT (kod) DO NOTHING;
COMMIT;
