BEGIN;
INSERT INTO core.departman
    (kod, ad, aile, misyon, durum, veri_kaynagi, otonomi_tavani, escalation)
VALUES
    ('WEB', 'Web / Dönüşüm', 'ALTYAPI',
     'Ürün satış sayfalarının kapsamını, dönüşümünü ve site sağlığını ölçer; değişiklik önerilerini sahibin onayına sunar.',
     'KISMI', 'core.urun_seo + mart.sayfa_olcum + mart.ecommerce_funnel',
     'L1', 'Yayın veya site değişikliği için sahip onayı gerekir')
ON CONFLICT (kod) DO NOTHING;
COMMIT;
