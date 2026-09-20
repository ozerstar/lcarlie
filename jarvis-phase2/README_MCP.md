# MCP sunucusu — Company Memory'yi dış istemciye açar

**Kuruldu:** 20.09.2026 · **Durum:** SALT OKUNUR (v1) · **Dosya:** `mcp_server.py`

## Ne işe yarar

Claude Code (veya MCP konuşan başka bir istemci) şirket verisine doğrudan
araç olarak ulaşır. Öncesinde tek yol elle `ssh lcarlie` + `docker exec psql`
yazmaktı — yani SQL'i elle kurmak, yani allowlist'in dışına çıkmak.

## 🔴 Üretim venv'ine DOKUNULMADI

`mcp` paketi **ayrı** `venv-mcp/` içinde. Sebep ölçüldü: ana venv'e kurmak
13 paket (starlette, uvicorn, opentelemetry, jsonschema…) ekliyordu ve o venv
`jarvis-web.service`'i, yani canlı `jarvis.lcarlie.shop`'u çalıştırıyor.
Kreatif analizi için alınmayacak bir risk.

```
venv/       -> jarvis-web.service, testler   (mcp YOK, olması da gerekmiyor)
venv-mcp/   -> yalnız mcp_server.py          (mcp==2.2.0)
```

## Güvenlik — üç katman, hiçbiri yeni değil

1. `CompanyMemory._fetch` allowlist dışı adı `ValueError` ile reddeder.
2. Kullanıcı metni SQL'e **hiç** girmez; sorgu adı sabit sözlükte anahtar.
3. Her sorgu `SET SESSION AUTHORIZATION ai_reader` + `ROLLBACK` içinde koşar.

Doğrulandı: `sirket_verisi(sorgu="DROP TABLE core.karar")` → `IZINLI_DEGIL`.

**v1'de yazma aracı YOK.** Hatırlatma eklemek (`core.acik_soru` INSERT) ayrı
rol ve ayrı karar ister; `EXTERNAL_ACTIONS=false` duruşuyla tutarlı olsun diye
konmadı. `test_yazma_araci_YOKTUR` bunu bekçilik eder — yazma aracı eklenirse
test kırılır.

## Araçlar

| Araç | Ne yapar |
|---|---|
| `sirket_sorgulari()` | 29 izinli sorgunun adı + ne içerdiği |
| `sirket_verisi(sorgu, limit)` | Allowlist'teki bir sorguyu çalıştırır |
| `gundem(limit)` | Açık sorular, önceliğe göre |
| `kreatif_performansi(limit)` | Başlık/CTA/biçim performansı + frekans |

## 🔴 "SORAMADIM" ≠ "VERI_YOK"

Her cevapta `durum` alanı var:
- `OK` — satır döndü
- `VERI_YOK` — sorgu çalıştı, gerçekten 0 satır
- `SORAMADIM` — sorgu çalışamadı, sonuç **bilinmiyor** (sıfır değil)
- `IZINLI_DEGIL` — allowlist dışı ad

Bu ayrım bu projede ölçülmüş bir tuzaktan geliyor: başarısız sorgu "sıfır"
diye okunursa yanlış karar verilir.

## Boyut tavanı

Cevap 12.000 karakteri aşarsa satır atılır ve `kirpildi` alanıyla **söylenir**.
Sessiz kırpma, eksik veriyi tam veri gibi göstermek olurdu.

## İstemci yapılandırması

Windows'ta `C:\Users\ozery\.mcp.json`:

```json
{ "mcpServers": { "lcarlie": {
    "command": "ssh",
    "args": ["-T", "-q", "lcarlie",
      "/opt/lcarlie/jarvis-phase2/venv-mcp/bin/python /opt/lcarlie/jarvis-phase2/mcp_server.py"]
}}}
```

`-T` (tty yok) ve `-q` (banner yok) **zorunlu** — ikisi de stdout'a bir şey
düşürüp JSON-RPC akışını bozabilir.

## Test

```
venv-mcp/bin/python scripts/run_mcp_smoke.py          # uctan uca, 7 kontrol
venv-mcp/bin/python -m unittest tests.test_mcp_server  # 7 birim testi
```

`tests/test_mcp_server.py` ana venv'de **atlanır** (mcp orada yok) — bu
tasarım, arıza değil. Ana takım: 797 test, OK (25 skip).

## Bilinen tuzak — bizi ilgilendirmiyor

Python MCP SDK'sının istemcisi Windows'ta `ssh`'ı başlatamıyor
("Connection closed", ssh stderr'i hiç çıkmıyor). Yerel süreçle aynı SDK
sorunsuz çalışıyor, ham JSON-RPC de ssh üzerinden sorunsuz gidiyor.
**Claude Code kendi Node istemcisini kullanıyor ve yapılandırmayı sorunsuz
yüklüyor** (`claude mcp list` → sunucu görünüyor). Yani bu, Python SDK'nın
Windows kusuru; bizim yolumuzu etkilemiyor.
