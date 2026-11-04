# lcarlie: üretim yetki (ACL) karşılaştırma paketi

Yerel veritabanı, üretimden `--no-owner --no-acl` ile alınmış schema-only bir dump'tan kuruldu. Bu yüzden üretimdeki gerçek yetkiler yerelde yok. `sql/03-grants-from-contract.sql` içindeki bazı yetkiler de tahmine dayanıyor. Bu paket üretimdeki gerçek durumu **salt okunur** biçimde toplar ve yerel veritabanıyla otomatik olarak karşılaştırır.

Paketteki hiçbir dosyada sunucu adresi, kullanıcı adı ya da parola yok. Üretim tarafını sen çalıştırırsın, bağlantı bilgisini de sen verirsin.

## Dosyalar

| Dosya | Nerede çalışır | Ne yapar |
|---|---|---|
| `acl-envanter.sql` | üretim + yerel | Rolleri, üyelikleri, veritabanı/şema/tablo/kolon/fonksiyon/tip yetkilerini, varsayılan yetkileri, sahipleri, RLS'yi, fonksiyon niteliklerini (SECURITY DEFINER, search_path) ve gövde md5'lerini, eklentileri, `core.ai_orchestrator_config` ile `core.ai_action_type` satırlarını `bolum\|nesne\|...` biçiminde, normalize edilmiş satırlar olarak döker. `BEGIN TRANSACTION READ ONLY` içinde çalışır, sonunda ROLLBACK eder. |
| `uretimde-topla.sh` | üretim (bash) | Salt okunur oturumla şunları üretir: `pg_dumpall --roles-only --no-role-passwords` → `roles.sql`, `pg_dump --schema-only` (sahiplik ve ACL dahil) → `schema-acl.sql`, `acl-envanter.txt`, `bilgi.txt`, `SHA256SUMS`. `roles.sql` içinde parola ya da hash izi bulursa dosyayı siler ve durur. |
| `karsilastir.sh` | yerel (Git Bash) | Aynı envanteri ve dump'ları yerelde `lcarlie-pg` container'ından alır, normalize eder ve fark çıkarır. `lcarlie-pg-local` container'ına dokunmayı reddeder. |
| `yerel-cikti/` | | Yerel tarafın son çıktısı (karşılaştırma her çalıştığında yenilenir). |

### Normalizasyon
- Kurulumu yapan süper kullanıcı (oid 10; yerelde `lcarlie_admin`, üretimde büyük olasılıkla `postgres`) her iki tarafta da `<bootstrap_superuser>` olarak yazılır. Dump'larda da adı buna çevrilir.
- NULL ACL, PostgreSQL'in varsayılan ACL'si (`acldefault`) açılarak yazılır. Böylece "hiç GRANT yok" ile "açıkça varsayılana eşit" durumları aynı görünür.
- Grantor yazılmaz. pg_dump'taki `GRANTED BY` kısmı silinir.
- `pg_*`, `information_schema` ve eklentiye ait nesneler dışarıda bırakılır.
- CRLF ve satır sonu boşlukları temizlenir. Satırlar `LC_ALL=C` ile sıralanır.
- Ayar değerlerinde anahtar adı secret/token/password/api_key/credential içeriyorsa değer maskelenir.

## 1) Üretimde çalıştır (sen, sunucuda)

PostgreSQL 17 istemcisi gerekli (`psql`, `pg_dump`, `pg_dumpall`). `pg_dump` sürümü sunucudan eski olamaz; betik bunu denetler. Kullanılacak rol bütün tablolarda ACCESS SHARE kilidi alabilmeli (pg_dump bunu ister) ve `core.ai_orchestrator_config` ile `core.ai_action_type` tablolarını okuyabilmeli. Pratikte bu, şemanın sahibi ya da süper kullanıcıdır. Rol bir şey yazmaz: tüm oturumlar `default_transaction_read_only=on` ile açılır ve betik bunu doğrular.

Üretim dump'ının başlığına göre kaynak veritabanının adı `n8n` (`pg_restore -l` → `dbname: n8n`). Çalıştırmadan önce doğrula.

```bash
# paketi sunucuya kopyala (adresi sen yaz):
scp -r prod-acl-karsilastirma <kullanici>@<sunucu>:/tmp/lcarlie-acl

# sunucuda:
cd /tmp/lcarlie-acl
export PGDATABASE=n8n        # dump başlığındaki ad; farklıysa düzelt
export PGUSER=<rol>          # şema sahibi ya da süper kullanıcı
# export PGHOST=... PGPORT=...   # yalnızca unix socket değilse
bash uretimde-topla.sh uretim-cikti
```

Sunucuda yerel bağlantı `peer` kimlik doğrulamasıyla yapılıyorsa şunu da kullanabilirsin:

```bash
sudo -u postgres env PGDATABASE=n8n bash uretimde-topla.sh /tmp/lcarlie-acl/uretim-cikti
```

Betiği kullanmadan aynı işi elle yapmak istersen tam komutlar şunlar:

```bash
export PGOPTIONS="-c default_transaction_read_only=on -c lock_timeout=10s"
pg_dumpall --roles-only --no-role-passwords -l "$PGDATABASE" -f roles.sql
pg_dump --schema-only --no-comments -f schema-acl.sql            # --no-owner / --no-acl YOK: sahiplik ve ACL dahil
psql -X -At -F '|' -v ON_ERROR_STOP=1 -f acl-envanter.sql > acl-envanter.txt
grep -E '^ayar_kontrol\|' acl-envanter.txt                       # orchestrator_enabled_after
```

Paylaşmadan önce `roles.sql` içindeki `ALTER ROLE ... SET` satırlarını gözden geçir. Parola ve hash bu dosyaya girmez, ama rol düzeyindeki ayarlar girer.

**F0-B taban SQL'i için ipucu:** `Documents\Codex\2026-09-18\...\docs\baseline\ROLLBACK_INDEX_V1.md` dosyasında F0-B geri alma betiğinin sunucudaki yolu `/root/lcarlie-f0b-rollback-20260917.sql` olarak geçiyor. Uygulama betiği de büyük olasılıkla aynı yerde. Sunucuda salt okunur kontrol için:

```bash
ls -la /root/lcarlie-f0b* /root/*f0b* 2>/dev/null
```

## 2) Yerelde karşılaştır (bu makine, Git Bash)

`uretim-cikti` klasörünü bu klasörün altına kopyala, sonra:

```bash
cd /c/Users/ozery/lcarlie-local/prod-acl-karsilastirma
bash karsilastir.sh uretim-cikti
```

Sonuç `fark-YYYYMMDD-HHMMSS/` klasörüne yazılır:
- `OZET.txt`: `orchestrator_enabled_after` değeri, bölüm bölüm fark sayıları, 03 dosyasındaki **6 tahmini yetkinin** üretimde olup olmadığı, kill-switch/ayar/action_type farkları ve rol/üyelik farkları
- `acl-envanter.diff`, `yalniz-uretimde.txt`, `yalniz-yerelde.txt`: ana karşılaştırma
- `schema-acl.diff`: pg_dump'taki GRANT/REVOKE/OWNER/DEFAULT PRIVILEGES satırlarının farkı
- `roles.diff`: pg_dumpall rol tanımlarının ve üyeliklerinin farkı

Yalnızca yerel tarafı denemek için: `bash karsilastir.sh --yalniz-yerel`

### Beklenen (zararsız) farklar
- `local_approver_1` rolü ve `human_approver` üyeliği yalnızca yerelde var.
- `core.ai_get_pending_actions()` için `fonksiyon_govde` md5'i farklı çıkar: yerelde `05-fix-pending-actions-order.sql` uygulandı (`958df0bc...`), üretimdeki gövde `ecbab115...`.
- `ayar|...|cutoff_version` yerelde seed ile eklendi. Üretimde aynı değer olmayabilir.
- Üretimde yerelde olmayan LOGIN rolleri (n8n'in giriş rolü gibi) görünebilir.

### Farkı yerele taşımak
Farkı otomatik uygulayan bir şey yok, bilerek. `yalniz-uretimde.txt` ve `schema-acl.diff` incelendikten sonra gerekli GRANT'lar `sql/03-grants-from-contract.sql` dosyasına elle eklenir ve yerelde yeniden kurulum yapılır. İnsan onayı, iki kişilik kritik onay ve kill-switch varsayılanları (`ai_worker_enabled=false`) üretimde başka değerde görünse bile yerelde gevşetilmemelidir.

## Yerel doğrulama (2026-10-26)
- `bash karsilastir.sh --yalniz-yerel`: çıkış kodu 0, 4.484 envanter satırı (3.538 `iliski_acl`, 502 `iliski_sahip`, 106 `fonksiyon`, 167 `fonksiyon_acl`, 10 `rol`, 3 `uyelik`, 23 `sema_acl`...). `orchestrator_enabled_after` = `ANAHTAR_YOK`. `roles.sql` içinde parola ya da hash yok.
- `uretimde-topla.sh` yerel container içinde (unix socket, `PGDATABASE=lcarlie`) uçtan uca çalıştırıldı. Çıktısı `karsilastir.sh`'a verildiğinde fark 0 satır çıktı (normalizasyon deterministik).
- Değiştirilmiş sahte bir "üretim" kopyasıyla (bootstrap `postgres`, `core.karar` SELECT yok, `orchestrator_enabled_after` var, `local_approver_1` yok) yapılan test, dört farkı da doğru raporladı. Bootstrap adının farklı olması fark üretmedi. Test kopyası sonra silindi.
