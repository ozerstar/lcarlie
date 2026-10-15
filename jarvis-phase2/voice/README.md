# Türkçe ses tanıma kontrolü

`terminology.py` içindeki kısa liste, yerel Whisper modeline Jarvis ve ürün
adlarını tanıtır. Modelin farklı duyduğu, ölçümle doğrulanmış birkaç biçim
ayrıca düzeltilir. Yeni eşleşme eklerken normal bir sözcüğü ürüne çevirmediğini
kontrol edin.

Sunucuda tekrar edilebilir örnek kontrolü:

```sh
cd /opt/lcarlie/jarvis-voice-agent
.venv/bin/python benchmark_stt.py --synthetic
```

Gerçek doğruluk için kullanıcının izin vererek sağladığı WAV kayıtlarını aynı
komuta dosya adı olarak verin. Betik ses dosyalarını dışarı göndermez; sonuçta
ham metin ve işlem süresi görünür. Sentetik ses, gerçek iPhone mikrofonu ve
gürültülü ortam ölçümünün yerini tutmaz.
