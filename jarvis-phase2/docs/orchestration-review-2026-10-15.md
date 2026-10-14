# Jarvis orkestrasyon incelemesi — 15 Ekim 2026

Bu not, beş projenin Jarvis'e uygulanabilir fikirlerini ayırır. Dış projeler çalıştırılmadı veya Jarvis'e bağımlılık olarak kurulmadı. Karşılaştırma, depoların bu tarihteki kodu ve Jarvis'in mevcut `execution_planner`, `execution_runtime`, `loop`, `coding_executor` ve onay sınırı üzerinden yapıldı.

| Kaynak | İncelenen mekanizma | Jarvis'teki karşılığı ve karar |
| --- | --- | --- |
| [AI-Research-SKILLs](https://github.com/Orchestra-Research/AI-Research-SKILLs/tree/main/0-autoresearch-skill) | Hızlı deney döngüsü, dönemsel sentez, ölçülebilir hipotez ve uzman yöntemi yönlendirme | `docs/improvement-loop.md` ve düzeltme defteri zaten var. 98 beceriyi topluca yüklemek yerine, belirli iş akışı için ölçütü ve kullanılan yöntemi kayıt altına almak gerekir. |
| [OrchestratorInc/agent-orchestrator](https://github.com/OrchestratorInc/agent-orchestrator) | Proje planlayıcısı ile izole işçi ayrımı; canlı durum, inceleme ve geri bildirimin tek görevde toplanması | `CodingExecutor` zaten atılabilir kopyada çalışıyor. Bir sonraki adım, görev/kanıt/onay durumunu tek izlenebilir kimlikte göstermek; ikinci bir ajan platformu kurmak değil. |
| [openark/orchestrator](https://github.com/openark/orchestrator) | Topoloji durumuna dayalı arıza saptama, opt-in kurtarma, denetlenebilir failover | Bu yazılım MySQL replikasyonu içindir; Jarvis'in PostgreSQL/ajan akışına kurulmaz. Yalnızca “önce gerçek durumu ölç, otomatik kurtarmayı açık izinle aç” ilkesi alınır. |
| [ralph-orchestrator](https://github.com/mikeyobrien/ralph-orchestrator/blob/main/crates/ralph-core/src/loop_lock.rs) | Aynı çalışma alanında eşzamanlı döngüyü dosya kilidiyle engelleme | Jarvis çalıştırma kaydı tamamlandıktan sonra yinelenen çağrıyı önlüyordu; eşzamanlı başlayan iki çağrı ise aynı işi iki kez yapabilirdi. Bu turda çalışma kimliği başına süreçler arası kilit eklendi. |
| [agency-orchestrator](https://github.com/jnMetaCode/agency-orchestrator/blob/main/README.en.md) | Bağımlılık DAG'ı, adım bazlı kabul ölçütü, insan onayı ve başarısız adımı sürdürme | DAG, sınırlı paralellik, kalıcı kayıt, sürdürme ve insan onayı zaten mevcut. Sonraki iş: adım çıktısı için doğrulanabilir kabul ölçütleri ve yalnız geçerli kanıtla “tamamlandı” deme. |

## Bu turda uygulanan

`ExecutionRuntime.execute` aynı `run_id` için non-blocking `flock` alır. İkinci işçi açık bir `ExecutionDenied` ile durur; ilk işçi bittiğinde kilit dosya tanıtıcısı kapanınca serbest kalır. Kilit, dosyaya yazma ve resume kararından önce alınır; farklı çalışma kimlikleri birbirini engellemez. Eylem/onay yetkileri değişmez. Aynı çalışma için paralel iki işçi testi eklendi.

## Sıradaki güvenli aşamalar

1. **Kabul sözleşmesi:** Her plan adımına ölçülebilir çıktı koşulları tanımla; eksik veri ve kanıtı başarısız/eksik olarak göster. Serbest metinli model değerlendirmesini tek doğruluk kaynağı yapma.
2. **Operasyon görünürlüğü:** Plan kimliği, çalışan adım, engel nedeni, kaynak, ölçülen süre ve insan kararını web/mobilde aynı görev kartına bağla. Gösterilen durum yalnız kalıcı kayıttan gelsin.
3. **Kontrollü yeniden deneme:** Yalnız geçici okuma hataları için sınırlı deneme ve geri çekilme uygula; dış eylemi, kod değişikliğini veya onay adımını otomatik tekrarlama.
4. **Ölçüm:** Önce/sonra çift çalıştırma, eksik kanıt, durdurulan tehlikeli eylem ve insanın düzelttiği öneri oranlarını ayrı izle. Bunları ticari başarı olarak adlandırma.

## Korunan sınırlar

İnsan kökeni olmadan çalışma başlamaz; kod görevleri ayrı atılabilir kopyada kalır; dış iş eylemi otomatik yürütülmez; stok/maliyet kayıtları ve mevcut onay hattı bu incelemede değiştirilmez. MySQL failover veya dış beceri paketleri kurulmaz.
