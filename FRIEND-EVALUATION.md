# Jarvis değerlendirme kopyası

Bu dal, 15 Ekim 2026 tarihinde kaynak depodaki kodun anlık kopyasıdır. Git geçmişini değil, o tarihteki dosya içeriklerini taşır. `live-overlay/`, canlı sunucuda bulunan fakat kaynak kopyasından farklı olan veya kaynakta bulunmayan **kod** dosyalarını ayrıca saklar. Bu klasör otomatik uygulanmaz; farkları inceleyip yalnız gerekenleri seçin.

Bu kopya üretim verilerini, erişim anahtarlarını, `.env` dosyalarını, sanal ortamları, müşteri kayıtlarını ve çalışma durumu klasörünü içermez. Buna rağmen kod L'CARLIÉ için yazılmış iş kuralları ve dosya yolları taşır; başka şirkette doğrudan üretime alınmamalıdır.

Deneme için önce kendi veritabanınızı, izinlerinizi ve entegrasyon anahtarlarınızı ayrı kurun; örnek yapılandırma dosyalarını kendinize göre doldurun. Dış eylemler ve müşteri iletişimi için insan onayı kapısını koruyun. Testleri proje sanal ortamında çalıştırın: `venv/bin/python -m unittest discover -s tests -q`.
