# Kadrosuz birimleri kanıtla etkinleştirme — 15 Ekim 2026

## Dış proje seçimi

| GitHub projesi | Kullanılan ilke | Kurulum kararı |
| --- | --- | --- |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Kalıcı durum, insan onayı öncesi durma ve yeniden başlatmada işin tekrarlanmaması | Jarvis'in mevcut kalıcı ekip raporu ve onay kapısı korunur; ikinci bir çalışma motoru eklenmez. |
| [Prefect](https://github.com/PrefectHQ/prefect) | Görev sonucu, zamanlayıcı ve hata durumunu ayrı izleme | Mevcut systemd ekip zamanlayıcısı ve `team-cycle/latest.json` kullanılır; ek sunucu kurulmaz. |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Rolün görevi ve kullanabildiği araç/veri açık tanımlanır | Her yeni rol yalnız izinli Company Memory sorgularına bağlanır; serbest araç erişimi verilmez. |
| [Meta Business SDK](https://github.com/facebook/facebook-python-business-sdk) ve [Google Ads Python](https://github.com/googleads/google-ads-python) | Resmî kanal API'leri | Gerekli izin ve yetkili veri akışı olmadan kurulup “aktif” gösterilmez. Mevcut bağlantılar korunur. |

Bu turda dış depo kodu kopyalanmadı ve yeni paket kurulmadı. Seçilen görev/kanıt ilkeleri mevcut Jarvis çalışma hattına uygulandı.

## Etkinleştirilen okuma görevleri

| Birim | Yeni görev | Kaynak | Sınır |
| --- | --- | --- | --- |
| Müşteri hizmetleri | Yanıtsız görüşme ve ürün bilgi kapsamını izleme | `crm_unanswered`, `urun_bilgi` | Yanıt göndermez; mesaj metni okumaz. |
| Müşteri araştırması | Anonim müşteri konularını sayma | `customer_voice` | Kişisel mesajları okumaz. |
| Deneyler | Hipotezlerin ölçüm/yanlışlama hazırlığını denetleme | `creative_hypotheses` | Deney yapıldı veya başarılı oldu demez. |
| Karar hafızası | Öneri/karar/öğrenme kayıtlarının kapsamını izleme | `own_proposals`, `decision_outcomes`, `learning_loop` | Ayrı kayıtları kanıtsız eşleştirmez. |
| Instagram | Organik içerik sayısı ve kayıtlı etkileşimi izleme | `content_performance` | Erişim izni yok; oran hesaplamaz, yayın yapmaz. |
| Stok ve envanter | Wix stok alanının kapsamını izleme | `urun_bilgi` | Fiziksel depo stokunu temsil etmez, kayıt değiştirmez. |
| Video/UGC | Video biçimli geçmiş içerikleri brief girdisi olarak sayma | `content_performance` | UGC hakları veya yeni üretim doğrulanmadı. |
| Yeni ürün | Müşteri konuları, mevcut ürünler ve pazar bulgularından ön araştırma | `customer_voice`, `urun_karti`, `market_research` | Formülasyon veya mevzuat onayı vermez. |

Bu roller ekip döngüsünde yalnız kanıtlı kaynak okunursa tamamlanmış sayılır. Kaynak boşsa `VERİ YOK` / bekleme, sorgu hatasında hata gösterilir. `ÇALIŞTI` etiketi rutin okuma anlamına da gelebilir; gerçek mesai, model üretimi veya dış eylem anlamına gelmez.

## Henüz etkinleştirilmeyenler

İhracat, eczane/ana müşteri, talep tahmini, hukuk/KVKK, Google arama reklamları, influencer, TikTok, satın alma ve tedarik zinciri için yeterli yetkili kaynak veya görev sözleşmesi yok. Bu dokuz birime genel amaçlı sahte görevli atanmadı. Kanal kimliği, doğru API izni, veri sahipliği ve kabul ölçütü doğrulanınca ayrı ayrı açılmalıdır.

Tüm işlemler salt okunurdur. Dış yayın, mesaj, satın alma ve stok/maliyet değişikliği mevcut insan onay sınırının dışına çıkarılmadı.
