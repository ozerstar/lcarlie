# Gelişim döngüsü

Raporlar / Gelişim döngüsü: iş, sorumlu, son tarih, ölçüt ve hedef; uygulama kanıtı; önce/sonra ölçümleri; düzeltme belleği.
Mevcut iş için önce hedef belirleyin, gerçek uygulama tarihini ve kanıtını kaydedin, ölçüm aralığında bu uygulamayı kapsayın.
Onay ve dahili EXECUTED, dış uygulama veya ticari başarı sayılmaz. Değişim nedensellik kanıtı değildir.

Saatlik lcarlie-improvement-cycle.timer 20 canlı kaynak erişim/sözleşme kontrolünü çalıştırır ve veri eksiklerini rollere atar.
Ölçülen: kaynak erişimi, kayıt alanları, süre, gerçek sayfa ölçüm tarihi. Ölçülmeyen: model yanıt kalitesi, parasal maliyet.
Son iki değerlendirme karşılaştırılır. Eksik bağlantı için gerekli dış kimlik bilgisi olmadan görev tamamlanmış sayılmaz.

Düzeltme ve ölçülmüş dersler ilgili kelimelerle en fazla 3 kayıt/2500 karakter olarak iç yanıtlara eklenir; mevcut kuralları değiştirmez.
Bu işlem model ağırlığı eğitimi değildir. Aynı hata için son düzeltme tercih edilir.
Defter: state/improvement/ledger.sqlite3; WAL dosyalarıyla birlikte yedekleyin. İşletme verisinin kaynağı mevcut PostgreSQL'dir.
Elle çalıştırma: JARVIS_MEMORY_TRANSPORT=local-docker venv/bin/python scripts/improvement-cycle.py
Durum: systemctl status lcarlie-improvement-cycle.timer
API: oturumlu GET /api/improvement; oturum+CSRF ile POST /api/improvement (work, plan, application, measurement, correction).

Beş model kanıt yorumlama testi: venv/bin/python scripts/improvement-model-eval.py. Yalnız sunucunun 127.0.0.1:8099 yerel modeli kullanılır; dış sağlayıcı ve GPU tüneline geçiş kapalıdır. Model yanıtı, kaynak referansı, jetonlar ve süre ayrı kaydedilir. Genel model başarısı iddia edilmez.
