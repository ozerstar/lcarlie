# L'CARLİÉ Radar — Jarvis'in proaktif katmanı

Sizin sormanızı beklemeden her gün çalışır; Özer'e sabah özeti gönderir, karar gerektiren şeyler için onay ister.

| Modül | Ne zaman | Ne yapar |
|---|---|---|
| Rakip radarı | Her gün 05:00 + 06:00 teyit | Jarvis ajanı yeni markaları bulur, Radar doğrular, filtreler, puanlar |
| Anlık uyarı | Teyit edilince | Büyük indirim (≥%20) veya yeni ürün → WhatsApp |
| Aylık rapor | Her ayın 1'i | İzlenen markalarda fiyat/ürün/kanal/reklam/büyüme değişimi |
| Müşteri adayı | Her gün 06:35 | Google Maps'ten eczane/klinik/güzellik merkezi + mesaj taslağı (onaya düşer) |
| Mevzuat | Her gün 06:25 | TİTCK duyurularında yeni satır |
| İçerik | Pazartesi | 7 günlük Instagram taslağı, TİTCK ön taramasından geçer |
| Sabah özeti | Her gün 07:00 | Hepsi tek mesajda |
| Sağlık + yedek | Pazartesi / her gece | Taranamayan kaynaklar, veritabanı bütünlüğü, 14 günlük yedek |

## Hatasızlık kuralları (kodla zorunlu)
- Kaynak linki ve tarama saati olmayan bilgi **reddedilir**.
- Fiyat/yorum/reklam sayısı, sayfadan kopyalanan alıntıda geçmiyorsa **reddedilir** (uydurma koruması).
- İzlenen markada büyük fiyat değişikliği ve yeni ürün, **farklı bir taramada** tekrar görülmeden uyarıya dönmez. Tek seferlik hatalı okuma otomatik iptal olur.
- Yeni markalar **aday** olarak gelir; siz onaylamadan izlemeye alınmaz. Reddettiğiniz marka bir daha önerilmez.
- Üçüncü kişilere giden hiçbir mesaj sizin onayınız olmadan gönderilmez.
- Her markanın puanı kriter kriter gösterilir (`radar marka <id>`).

## Kurulum (Jarvis sunucusu)
```bash
scp lcarlie_radar.zip lcarlie:/opt/lcarlie/
ssh lcarlie
cd /opt/lcarlie && unzip lcarlie_radar.zip -d radar && cd radar
cp config.example.json config.json      # WhatsApp numaranızı yazın
cp deploy/env.example .env && chmod 600 .env   # anahtarları girin
chmod +x deploy/run.sh && ln -sf deploy/run.sh run.sh
python3 -m unittest discover -s tests   # 15 test geçmeli
./run.sh init
cp deploy/lcarlie-radar.cron /etc/cron.d/lcarlie-radar
```
Python 3.8+ yeterli, ek paket gerekmez.

**Jarvis bağlantısı (tek adım):** `.env` içine Jarvis'te rakip ajanını başlatan komutu ekleyin:
`JARVIS_AGENT_CMD="python3 /opt/lcarlie/jarvis-phase2/<ajan_betiği>.py"`
Ajan `--mode tarama|teyit --task TASK.md --recheck scans/teyit.json --watch scans/izlenen.json --out <dosya>` parametrelerini alıp TASK.md'deki JSON formatında çıktı yazmalı.

WhatsApp: `JARVIS_WHATSAPP_WEBHOOK` girilirse mesajlar oraya POST edilir (`{"to","text","outbox_id"}`); girilmezse `outbox/` klasörüne JSON olarak düşer, Jarvis oradan okur.

## Günlük kullanım
```bash
python3 -m radar adaylar                       # onay bekleyen markalar
python3 -m radar marka 12                      # puan dökümü + kaynaklar
python3 -m radar onayla-marka 12 15            # izlemeye al
python3 -m radar reddet-marka 13 --neden "alakasız" --kelime "saç boyası"
python3 -m radar mesajlar                      # onay bekleyen mesajlar (lead)
python3 -m radar onayla-mesaj 7                # gönderilsin
python3 -m radar iddia-kontrol "metin"         # TİTCK ön tarama
python3 -m radar ozet-onizle                   # özeti göndermeden gör
```

Satış verisi: Jarvis `data/satis_ozet.json` dosyasına `{"Dün sipariş": 14, "Trendyol": "8.420 TL"}` gibi yazarsa sabah özetine eklenir.

Fiyat bandı referansı `data/fiyat_listesi.json` (L'CARLİÉ satış fiyat listesi, PSF). Fiyat değişince bu dosyayı güncelleyin.

> TİTCK taraması bir ön filtredir, hukuki inceleme yerine geçmez.
