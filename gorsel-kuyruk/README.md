# Görsel kuyruğu ve sıra hakemi

## Neden var — ölçüldü 24.09.2026

PC-2'nin (RTX 5060) VRAM'i **8.151 MiB**. Gereken:

```
masaüstü        1,7 GB
Qwen3-8B        5,8 GB
ComfyUI / SDXL  2,5-2,9 GB
               ─────────
toplam         ~10,4 GB   >   8,15 GB
```

Büyük dil modeli ile görsel üretimi **aynı anda sığmıyor**. Bu yüzden PC-2'de
iki kip var ve aralarındaki geçişi `jarvis-hakem.ps1` yönetir.

| Kip | Ne çalışır | Sunucudaki port |
|---|---|---|
| LLM (varsayılan) | `llama-server` Qwen3-8B | 8097 |
| GÖRSEL | ComfyUI + SDXL | 8095 |

> **25.09.2026 GÜNCELLEME — 8097 artık model zincirinin ayağı DEĞİL.**
> Jarvis'in GPU kademesi (`JARVIS_GPU_MODEL_URL`) o gün PC-1'e taşındı:
> `127.0.0.1:8098`, Qwen3-4B, sunucudan tünelle ölçülen **~55-66 t/sn**.
> Buradaki 8097 yalnız PC-2'nin kendi kipi olarak duruyor; hakem görsel
> işine geçtiğinde kapanır ve **kapanması artık zinciri etkilemez**.
> Panelin TÜNELLER göstergesi bu yüzden 8097'yi izlemez — izleseydi her
> gün yanlış alarm verirdi.

## Ölçülen döngü

Tek görsel işi, uçtan uca:

```
05:40:36  iş görüldü, LLM durduruldu
05:40:52  ComfyUI hazır            (16 sn)
05:41:18  görsel üretildi          (22 sn)
05:41:38  kuyruk boşaldı
05:42:01  LLM tüneli geri kuruldu
──────────────────────────────────
LLM kesintisi: 85 saniye
```

**Bir görsel işi 85 saniyelik LLM kesintisi demektir.** Bu bir hata değil,
tasarımın bilinen bedeli. Toplu iş verirken bunu hesaba kat.

## Kullanım

```bash
# iş ekle
/opt/lcarlie/gorsel-is-ekle.sh "<istem>" [adet] [negatif]

# durum
/opt/lcarlie/gorsel-kuyruk-durum.sh
```

Dizinler: `/opt/lcarlie/gorsel-kuyruk/{bekleyen,calisan,biten,hata,cikti,log}`

## Güvenlik özellikleri

- **Tavan.** GÖRSEL kipinde en fazla 30 dakika kalınır; kuyruk dolu olsa bile
  LLM'e dönülür. LLM'in süresiz aç kalması kabul edilemez.
- **Her hata yolu LLM'e döner.** "Ne LLM ne görsel" durumu oluşamaz.
- **Önce taşı, sonra işle.** İş `bekleyen/` → `calisan/` taşınır, sonra
  işlenir. Çökme hâlinde aynı iş iki kez üretilmez; `calisan/` içinde asılı
  kalır ve görülür.

## Neden dosya kuyruğu, neden Postgres değil

v1'de bilinçli tercih: Postgres şeması + grant + PC-2'ye Python paketi kurmak
yerine SSH üzerinden okunan bir dizin. Denetlenebilir (`ls` yeter), geri
alınabilir (dizini sil), bugün çalışır. Hacim gerektirdiğinde `procrastinate`
(PostgreSQL kuyruğu, "KOD AL" listesinde) doğal yükseltme yolu.

## Tekrarlanmayacak tuzaklar

1. **Anahtar NTFS'te olmak zorunda.** PC-2'de `C:\lcarlie-llama\ssh\`. exFAT
   dosya izni tutmaz; `icacls` sessizce hiçbir şey yapmaz ve OpenSSH anahtarı
   `bad permissions` diye reddeder. Belirtisi sinsi: günlükte "tunnel started"
   yazar ama süreç anında ölür.
2. **SSH oturumundan `Start-Process` ile başlatılan süreç ölür.** Bağımsız
   süreç için `Invoke-CimMethod Win32_Process Create` kullanılır.
3. **SYSTEM'in profili farklıdır.** `~/.ssh/config` okunmaz; bütün ssh
   seçenekleri betikte açıkça verilir.
