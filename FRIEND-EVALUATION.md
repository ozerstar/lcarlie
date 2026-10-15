# Jarvis kod inceleme kopyası

Bu dal 15 Ekim 2026 tarihinde güncellendi. Ana kaynak ağacındaki son izlenen kodu
ve canlı sunucuda kaynak ağacından ayrı duran seçili kod dosyalarını içerir.

## Nereden başlamalı?

- Proje açıklaması: `jarvis-phase2/README.md`
- Web ve mobil API: `jarvis-phase2/webconsole/app.py`
- Telefon arayüzü: `jarvis-phase2/webconsole/static/mobile/`
- Kişisel asistanın canlı sürüm farkları: `live-overlay/webconsole/`
- Bildirim göndericisinin canlı sürümü: `live-overlay/scripts/push-send.py`

`live-overlay/` dosyaları otomatik uygulanmaz. Kaynak ağacındaki karşılıklarıyla
karşılaştırıp gereken farkları seçin. Özellikle `personal_brief.py`,
`mobile_features.py`, `google_workspace.py` ve `action_ledger.py` Kişisel alanın
yakın zamanda eklenen özellikleridir.

Bu kopya üretim verilerini, erişim anahtarlarını, `.env` dosyalarını, sanal
ortamları, müşteri kayıtlarını ve çalışma durumu klasörünü içermez. Kodu
çalıştırmak için kendi veritabanınızı ve servislerinizi kurup örnek yapılandırma
dosyalarını doldurmanız gerekir. İşlem onaylarını kapatmayın.
