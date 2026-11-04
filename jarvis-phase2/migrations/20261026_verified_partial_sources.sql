-- Existing fixed read queries checked on 2026-10-26; no new external authorization.
BEGIN;
UPDATE core.departman SET durum='KISMI', veri_kaynagi=concat_ws(E'\n',NULLIF(veri_kaynagi,''),'26.10.2026 okuma doğrulaması: ecommerce_funnel; urun_karti; provenance — GA4 toplu huni ve ürün kayıtları; kullanıcı yolculuğu ve deney sonuçları kapsam dışı') WHERE kod='CRO' AND durum='YOK';
UPDATE core.departman SET durum='KISMI', veri_kaynagi=concat_ws(E'\n',NULLIF(veri_kaynagi,''),'26.10.2026 okuma doğrulaması: crm_customers; sales_orders — 33 müşteri ve 39 sipariş okunarak kontrol edildi; kimlik eşleştirme kapsamı kısmi') WHERE kod='RETENTION' AND durum='YOK';
UPDATE core.departman SET durum='KISMI', veri_kaynagi=concat_ws(E'\n',NULLIF(veri_kaynagi,''),'26.10.2026 okuma doğrulaması: customer_voice; crm_unanswered — anonim müşteri temaları ve yanıtsız mesaj kayıtları; üretim kalite sistemi bağlı değil') WHERE kod='QUALITY' AND durum='YOK';
UPDATE core.departman SET durum='KISMI', veri_kaynagi=concat_ws(E'\n',NULLIF(veri_kaynagi,''),'26.10.2026 okuma doğrulaması: customer_voice; urun_karti; market_research — iç kaynaklar ve kayıtlı pazar bulguları; sürekli dış araştırma bağlı değil') WHERE kod='RND' AND durum='YOK';
UPDATE core.departman SET durum='KISMI', veri_kaynagi=concat_ws(E'\n',NULLIF(veri_kaynagi,''),'26.10.2026 okuma doğrulaması: content_performance — 130 içerik kaydı; Instagram etiket izinleri ve içerik kullanım hakkı doğrulaması eksik') WHERE kod='UGC' AND durum='YOK';
COMMIT;
