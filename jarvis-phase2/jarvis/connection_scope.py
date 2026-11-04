"""Documented partial bindings, not claims of full external integration."""
SCOPES = {
 'CRO': ('ecommerce_funnel','urun_karti','provenance'),
 'RETENTION': ('crm_customers','sales_orders'),
 'QUALITY': ('customer_voice','crm_unanswered'),
 'RND': ('customer_voice','urun_karti','market_research'),
 'UGC': ('content_performance',),
}
LIMITATIONS = {
 'CRO':'GA4 toplu huni ve ürün kayıtları bağlı. Kullanıcı bazında yolculuk veya deney sonucu değildir.',
 'RETENTION':'Şirket siparişleri ve eşleşmiş müşteri kayıtları bağlı. Eksik müşteri kimlikleri sonucu etkileyebilir.',
 'QUALITY':'Anonim müşteri konu özetleri ve yanıtsız mesaj sayıları bağlı. Üretim kalite ve uygunsuzluk sistemi değildir.',
 'RND':'Şirket ürün/müşteri ve kayıtlı pazar bulguları bağlı. R&D için bağımsız sürekli dış araştırma kaynağı henüz bağlı değil.',
 'UGC':'İçerik performansı brief girdisi olarak bağlı. Instagram /tags izin engeli ve UGC kullanım hakkı doğrulaması devam ediyor.',
}
