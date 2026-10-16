# Tarayıcı Worker — Jarvis → Kuyruk → Bilgisayar → Chrome → Jarvis

Jarvis bir işi kuyruğa yazar; PC-1'deki worker SSH ile alır, kendi Chrome
profilinde ChatGPT/Claude'a yaptırır, sonucu geri yükler. Sonuç mevzuat
kapısından geçip **panelin onay kuyruğuna** düşer; Web Push telefona haber
verir. Onayı panelde verirsin.

```
Jarvis (sunucu) ──yazar──▶ core.tarayici_isi
                                   ▲ SSH (15 sn'de bir, dışa doğru)
                      Worker (PC-1, E:\jarvis-worker)
                                   │ Playwright, AYRI Chrome profili
                                   ▼
                       ChatGPT / Claude web arayüzü
                                   │
Worker ──SSH──▶ /opt/lcarlie/tarayici-cikti + core.tarayici_isi.sonuc_*
                                   │
lcarlie-tarayici.timer ──▶ mevzuat kapısı ──▶ jarvis-operator create-task
                                   │
jarvis-phase2.service ──▶ core.jarvis_action_registry (AWAITING_APPROVAL)
                                   │
lcarlie-push-approvals.timer ──▶ 📱 Web Push ──▶ panelde ONAY
```

---

## Neden böyle — mevcut yapıya oturan kararlar

**Kuyruk Postgres'te, Supabase'de değil.** Projede Supabase'in hiç izi yok
(`grep -ril supabase` → 0). Her şey `lcarlie-postgres` üzerinde ve güvenlik
modeli RLS değil **rol tabanlı** (`function_owner` / `ai_writer` /
`ai_reader` / `human_approver`, `REVOKE ALL FROM PUBLIC`, `SECURITY DEFINER`).
Supabase eklemek yeni bir dış servis, iki yeni anahtar ve **promptların +
üretilen görsellerin üçüncü tarafa gitmesi** demekti. PC'de SSH zaten vardı.

**`core.ai_task`'a GİRMEZ, ayrı tablo.** Ölçüldü: o tablonun iki `CHECK`
kısıtı bu işi kabul etmiyor (`task_type` 6 değerle, `source_type` 5 değerle
sınırlı). Kısıtı genişletmek 17 timer'ın paylaştığı kuyruğa dokunmak olurdu.
Kiralama deseni ise `core.ai_claim_task`'tan **birebir kopyalandı**
(`FOR UPDATE SKIP LOCKED` + tek CTE içinde `UPDATE`).

**Entegrasyon deseni yeni değil.** KREATIF_BRIEF, KREATIF_INCELEME ve
CODE_CHANGE_REVIEW ile aynı: iş döngünün DIŞINDA yapılır, sonuç diske
yazılır, `jarvis-operator create-task` görevi açar, `loop.py` öneriyi yazar.
`TARAYICI_SONUC` → `REQUEST_HUMAN_REVIEW`; **yeni bir DB action type
uydurulmadı** (kodun kendi kuralı).

**Nabız için yeni dosya açılmadı.** Panelin `TAZE / BAYAT / RAPOR_YOK`
sözlüğü `webconsole/sistem.py`'de tanımlı ve aynen kullanılıyor.
🔴 **BAYAT, makinenin KAPALI olduğunu KANITLAMAZ** — ağ da takılmış olabilir.
Panel bu yüzden teşhis değil gözlem+soru yazar.

**WhatsApp'a bağlanmadı.** `jarvis/whatsapp.py` müşteriye giden 5 kapılı bir
kanaldır ve 4. kapısı (`JARVIS_WHATSAPP_GONDER`) varsayılan KAPALI. Bu işi
ona bağlamak o anahtarı açmak demekti. Haber Web Push'tan gelir, onay
panelde verilir.

---

## Kurulum

### 1. Sunucu (bir kez)

```bash
# Göç
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 \
  -f - < /opt/lcarlie/jarvis-phase2/migrations/037_tarayici_isi.sql

# Çıktı dizini
mkdir -p /opt/lcarlie/tarayici-cikti && chmod 750 /opt/lcarlie/tarayici-cikti

# Zamanlayıcı
systemctl daemon-reload
systemctl enable --now lcarlie-tarayici.timer

# Panel (yeni /tarayici/ rotası için)
systemctl restart jarvis-web.service
```

Geri alma: `migrations/rollback/037_tarayici_isi_ROLLBACK.sql`
(🔴 tablo düşünce bekleyen işler de gider — önce kuyruğun boş olduğunu doğrula).

### 2. Bilgisayar (PC-1)

```powershell
# Worker E:\jarvis-worker altında. 🔴 C: KULLANILMAZ (%90 dolu),
# 🔴 D: KULLANILMAZ (exFAT — SSH anahtarı orada çalışmaz).
cd E:\jarvis-worker
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` sonunda ekrana bir satır yazar. Onu sunucuya ekle:

```bash
# /root/.ssh/authorized_keys içine, DİĞER ANAHTARLARA DOKUNMADAN
command="/opt/lcarlie/bin/tarayici-kapi",no-agent-forwarding,no-port-forwarding,no-pty,no-X11-forwarding,no-user-rc ssh-ed25519 AAAA... tarayici-worker@pc1
```

Sonra:

```powershell
.\start-chrome.ps1    # Chrome açılır → ChatGPT ve Claude'a BİR KEZ elle giriş yap
.\kur-gorev.ps1       # oturum açılınca otomatik başlayan görevleri kurar
```

Güç ayarı (yönetici PowerShell) — bilgisayar uyursa worker durur:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

### 3. Chrome profili

Worker **ayrı** bir profil kullanır: `E:\jarvis-worker\chrome-profile`.
Günlük Chrome'una dokunmaz. ChatGPT/Claude oturumu bu profilde durur;
**şifre koda yazılmaz, worker kimlik bilgisi görmez.**

---

## Kullanım

```python
from jarvis import tarayici

tarayici.enqueue_browser_task(
    "VIREON kutusunun yanında beyaz mermer zeminde ürün görseli üret",
    "chatgpt_image",                 # chatgpt_image | chatgpt_chat | claude_chat
    requested_by="tasarim-departmani")
```

Durum:

```python
tarayici.durum()       # sayılar + nabız + hatırlatma
tarayici.sayim()        # her durumun adedi
tarayici.nabiz()        # TAZE | BAYAT | RAPOR_YOK | OKUNAMADI
```

Merkezi anahtar — worker'ı PC'ye gitmeden kapatmanın tek yolu:

```sql
UPDATE core.ai_orchestrator_config
   SET config_value = 'false' WHERE config_key = 'tarayici_worker_enabled';
```

---

## Güvenlik sınırı

**Worker'a kabuk verilmez.** Anahtar `authorized_keys`'te zorunlu komuta
bağlı; o anahtarla yalnız altı alt komut çalışır (`al`, `girdi`, `bitir`,
`hata`, `insan`, `nabiz`). Ölçüldü:

| Deneme | Sonuç |
|---|---|
| `ssh ... "id"` | `izinli olmayan alt komut: 'id'` |
| `ssh ...` (interaktif) | `alt komut yok. izinli: al, bitir, girdi, hata, insan, nabiz` |
| `ssh ... "cat /etc/shadow"` | `izinli olmayan alt komut: 'cat'` |
| `al worker; rm -rf /tmp/x` | `kullanim: al <worker>` (kabuk kurulmuyor) |
| `hata "1; DROP TABLE ..."` | `is_id tam sayi olmali` |

**İkinci katman:** kapı hatalı olsa bile psql çağrıları `SET ROLE
tarayici_worker` ile koşar ve o rol iş alır/kapatır; iş **ekleyemez**,
`SUNULDU` **yazamaz**, tabloyu **okuyamaz** (ölçüldü: `permission denied
for table tarayici_isi`).

**Girdi dosyaları allowlist'li.** Keyfi yol reddedilir; kapı sunucuda
dosya okuma aracına dönüşemez.

**Sonuç dosyaları oturum kapısının arkasında.** `/tarayici/` rotası
`_route_kreatif` ile aynı kapı ve aynı yol-kaçışı kontrolünü kullanır:
onaylanmamış üretim açık internete düşmez.

---

## Mevzuat kapısı — İKİ YÖNLÜ

```
istem  → compliance.review() → BLOCKED ise kuyruğa HİÇ girmez (UyumEngelledi)
sonuç  → compliance.review() → BLOCKED ise öneri "BLOKLU" diye işaretlenir
```

Girişte durdurmak yetmez: temiz bir istem gidip "lekeleri tedavi eder" diye
bir cümle geri gelebilir.

🔴 **BLOKLU sonuç silinmez, gizlenmez.** Sahibin önüne "uyum kapısı
engelledi, metin şu" diye konur. Sessizce atmak, "üretilmedi" ile
"engellendi"yi aynı gösterirdi.

---

## Yedek yol

Handler katmanı **kırılgan olduğu bilinerek** yazıldı: ChatGPT/Claude
arayüzü haber vermeden değişir ve o arayüzleri otomatikleştirmek kullanım
şartlarına aykırı olabilir. Bu yüzden iş `HATA`/`INSAN_GEREKLI`'ye düşerse
sunucuda yedek denenir.

🔴 Yedek **sunucuda** koşar, PC'de değil (model zinciri ve ComfyUI kuyruğu
orada yaşıyor).

| Hedef | Yedek | Ölçüm (16.10.2026) |
|---|---|---|
| `claude_chat` | `providers.generate()` model zinciri | **ÇALIŞIYOR** (claude-haiku-4-5 ile doğrulandı) |
| `chatgpt_chat` | aynı zincir | **ÇALIŞIYOR** |
| `chatgpt_image` | ComfyUI kuyruğu / Higgsfield | **YOK** — ComfyUI'yi işleyen PC-2'nin son raporu 04.10.2026; Higgsfield anahtarı sunucuda tanımlı değil |

🔴 Görsel yedeği "var" gibi gösterilmiyor. Kuyruğa yazıp başarılı saymak,
işi kimsenin bakmadığı yere atmak olurdu; yokluk **sebebiyle** söyleniyor.

Yedeğin çıktısı öneride **ayrı bir bölümde** ve "bu metin ChatGPT/Claude
arayüzünden DEĞİL" notuyla durur.

---

## Arayüz bozulduğunda nereye bakılır

**Tüm CSS seçiciler ve arayüz adımları yalnız bu dosyalarda:**

```
E:\jarvis-worker\handlers\ortak.py           giriş/CAPTCHA tespiti, yazma, yanıt bekleme
E:\jarvis-worker\handlers\claude_chat.py     Claude seçicileri
E:\jarvis-worker\handlers\chatgpt_chat.py    ChatGPT seçicileri
E:\jarvis-worker\handlers\chatgpt_image.py   ChatGPT görsel + indirme
```

`worker.py` hiçbir seçici bilmez. Her seçici bir **liste**: arayüz değişince
hepsi birden kırılmaz, ve hiçbiri tutmazsa hata mesajı **hangi seçicilerin
denendiğini** yazar.

Teşhis: `E:\jarvis-worker\worker.log` ve her işin ekran görüntüsü
(`E:\jarvis-worker\ekran\`, 7 gün sonra silinir; sunucudaki kopyası öneride).

---

## Tuzaklar (tekrarlanmasın)

1. **CRLF.** Windows'ta yazılan `.py`/`.sh` sunucuya CRLF ile giderse
   shebang `python3\r` olur: `/usr/bin/env: 'python3\r': No such file`.
   Aktarırken `tr -d '\r'`.
2. **BOM'suz `.ps1`.** PowerShell 5.1 BOM'suz `.ps1`'i ANSI sanır; Türkçe
   karakter **ayrıştırma hatası** verir. `.ps1` dosyaları UTF-8 **BOM'lu**.
   Ayrıca PowerShell değişken adlarında Türkçe harf kullanılmaz.
3. **psql `-c` değişken yerleştirmez.** `:'ad'` sunucuya olduğu gibi gider
   ve `syntax error at or near ":"` olur. `-f -` + stdin kullanılır.
4. **`GRANT EXECUTE` tek başına yetmez.** Şema üzerinde `USAGE` yoksa
   `permission denied for schema core` alınır.
5. **`ssh-keyscan` bu makinede çalışmıyor.** Windows OpenSSH 9.5p1
   sunucunun KEX yöntemini desteklemiyor. `setup.ps1` host anahtarını
   zaten güvenilen `~/.ssh/known_hosts`'tan alır.
6. **exFAT'te SSH anahtarı çalışmaz.** `icacls` sessizce hiçbir şey yapmaz,
   OpenSSH "bad permissions" der. Worker NTFS'te (E:) durur.
7. **Worker SYSTEM olamaz.** Session 0'da görünür masaüstü yoktur, Chrome
   profili kullanılamaz. Görev `Interactive` + `AtLogOn`. ("Jarvis Metrik"
   görevi SYSTEM'dir ve öyle kalır — o tarayıcı gerektirmez.)
8. **Chrome'u worker başlatmaz.** Aynı profili iki süreç açamaz
   ("profile is already in use"). `start-chrome.ps1` başlatır, worker
   `connect_over_cdp` ile **bağlanır**.
9. **Chrome yolu sabit yazılmaz.** Bu makinede Chrome
   `C:\Program Files (x86)\...` altında; `Program Files` yolu yok.

---

## Ne olmadığı

- **Onay değil.** Hiçbir sonuç panelde onaylanmadan 3. kişiye gitmez.
- **CAPTCHA aşıcı değil.** Giriş/bot doğrulaması görülürse iş
  `INSAN_GEREKLI` olur ve **yeniden denenmez**.
- **Paralel değil.** Tek seferde tek iş; işler arası 10–30 sn rastgele
  bekleme (hesap kısıtları).
