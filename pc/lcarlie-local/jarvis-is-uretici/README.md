# Jarvis iş üretici

Ajanların "boş oturma" sorununa çözüm. Kök neden: zamanlanmış üreticilerin hepsi sıfır model çağrısıyla çalışıyordu; tablo sayıyor ama düşünmüyorlardı. Bu modül mevcut parçaları kullanır: şirket hafızası, ekip listesi (`roster`), araştırma notları, `providers.generate` model katmanı ve iş defteri (`improvement.Store`). Yeni bir platform kurmaz.

## Takvim

| Zamanlayıcı | Ne zaman | Ne üretir | Model kademesi |
|---|---|---|---|
| `aylik` | Her ayın 1'i, 11:20 | Holding hedef ağacı: 3-5 hedef, ölçüt ve katkı veren birimler | muhakeme (Claude) |
| `haftalik` | Pazartesi 10:40 | Departman başına haftalık rapor, 3 yeni fikir ve gelecek haftanın işleri | hızlı (Gemini) |
| `gunluk` | Her gün 10:05 | Departman başına 1-3 görev, 1 araştırma sorusu ve 1 bulgu | hızlı |
| `yurut` | 11:10'dan 21:10'a 2 saatte bir | Açık iç görevleri sorumlu üyeye yaptırır; teslimi kalite kapısından geçirir | hızlı (+ SearXNG canlı araştırma) |

## Nerede görünür

- **Jarvis web → Raporlar / Gelişim döngüsü:** her görev bir `work` kaydı olur (sahibi, kabul ölçütü, son tarihi). Teslim edilince `application` kanıtı düşer.
- **`state/is-uretici/agac.json`:** hedef → departman → görev ağacı.
- **`state/is-uretici/raporlar/<tarih>/<KOD>-gunluk|haftalik.md` ve `HOLDING-aylik.md`:** departman ve holding raporları.
- **`state/is-uretici/teslimler/<görev>.md`:** üyenin yazdığı teslim.
- **`state/is-uretici/ozet-<tarih>.md`:** günün özeti. Tebrik edilecek teslimler ve onayını bekleyen işler burada listelenir.

## Güvenlik

- **Dış eylem yok:** yayın, mesaj, fiyat, stok veya reklam gerektiren iş yalnız `ONAY_GEREKTIREN` olarak listelenir, hiçbir zaman yürütülmez.
- **Dış metin veridir:** araştırma metinleri `<veri>` içinde verilir. Enjeksiyon işaretli olanlar modele hiç gitmez. Çıktıdaki URL ve komut kalıpları ayıklanır.
- **Uydurma kayıt yok:** kanıt kimlikleri doğrulanır; uydurulmuş üye, birim ya da hedef kodu atılır.
- **Kalite kapısı:** teslimin en az 120 kelime olması, kanıta dayanması ve kabul ölçütünü karşılaması gerekir. Geçemeyen teslim deftere işlenmez; iki denemeden sonra `INSAN_INCELEMESI` durumuna düşer.
- **Kill-switch ve bütçe:** `/etc/lcarlie/is-uretici.env` içinde `IS_URETICI_ENABLED=false` ile kapatılır. Günlük çağrı tavanı `IS_URETICI_GUNLUK_TAVAN=160`.
- **Tahmini maliyet:** Gemini flash-lite ile günde yaklaşık 90 çağrı. Bu, ayda yaklaşık 8-15 USD eder; aylık Claude çağrısı ihmal edilebilir. Gerçek tutar maliyet defterinde (`usage`) görünür.

## Kurulum (sunucu)

```bash
scp -r C:/Users/ozery/lcarlie-local/jarvis-is-uretici lcarlie:/tmp/
ssh lcarlie 'bash /tmp/jarvis-is-uretici/kur.sh'
```

`kur.sh` sırayla şunları yapar:
1. Yedek alır (`/opt/lcarlie/backup-is-uretici-*`).
2. Aynı adlı farklı bir dosya varsa durur (Codex koruması).
3. Testleri ve kuru denemeyi çalıştırır.
4. Zamanlayıcıları açar ve ilk turu başlatır: aylık → günlük → haftalık → yürütme.

Geri almak için: `ssh lcarlie 'bash /tmp/jarvis-is-uretici/geri-al.sh'`.

## Test

`python -m unittest discover -s tests`: 10 test, sahte model ile, sıfır dış çağrı.
