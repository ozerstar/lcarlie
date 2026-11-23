# MCP güvenlik düzeltmesi — 23 Kasım 2026

## Doğrulanan kapsam

İncelenen kaynak: `ozerstar/lcarlie`, `main` commit `6489457`.
Bu inceleme canlı sunucuya erişim veya canlı paket sürümü doğrulaması değildir.

| Bileşen | Depoda görülen kayıt | Çıkarılamayan sonuç |
|---|---|---|
| RuFlo | `jarvis/capabilities.py`: UPSTREAM_BLOCKED; `adapter_factory.py`: UNAVAILABLE | Canlı makinede ayrıca kurulmuş olup olmadığı |
| OmniRoute | İncelenen depoda kurulum/sürüm kaydı bulunamadı | Sistemde yok veya güvenli olduğu |
| Agent Reach | Araştırma raporunda doğrulanmış adaptör olmadığı yazıyor | Canlı sürümü ve paket kaynağı |
| MCP-Scan / Invariant | İncelenen depoda kurulum/sürüm kaydı bulunamadı | Snyk Agent Scan'e geçişin yapıldığı |
| Jarvis MCP sunucusu | `mcp_server.py`, stdio; `requirements-mcp.txt`: `mcp==2.2.0` | Sunucunun gerçekten bu sabitlenmiş sürümü kullandığı |

`mcp` SDK paketi, MCP-Scan tarayıcısı ve RuFlo MCP köprüsü farklı bileşenlerdir.
Upstream advisory'ler Jarvis'in kendi MCP sunucusuna otomatik olarak uygulanamaz.

## Hazırlanan düzeltmeler

- Backend hata metni yerine sabit hata kodları: bağlantı URL'si, SQL veya müşteri
  bilgisi içerebilen istisna metinleri istemciye çıkmaz.
- Allowlist kontrolü sorgudan önce yapılır; izinli sorgunun dahili ValueError'ı
  yanlışlıkla IZINLI_DEGIL olarak sınıflandırılmaz.
- Satır limiti ve boyut tavanı yüzünden eksilen her yanıtta `kirpildi` döner.
  Büyük tek kayıt yüzünden boşalan sonuç, gerçek veri yokluğuyla karışmaz.
- Negatif/tam sayı olmayan limit reddedilir; sorgu backend'e ulaşmaz.
- Satır değerlerinin talimat veya işlem izni olmadığı sunucu talimatına ve
  yanıt metadatasına eklenir. Bu, tek başına injection engelleme garantisi değildir.
- Yanıt mantığı SDK'dan ayrılır; güvenlik testleri MCP paketi yokken de çalışır.
- `scripts/component_inventory.py`, açıkça belirtilen paket dizinlerindeki JSON ve
  Python METADATA dosyalarını metin olarak okur. Paket import etmez, `--version`
  çalıştırmaz, ağ/kurulum/güncelleme/servis değişikliği yapmaz.

## Envanterin kullanımı

Yalnız bilinen gerçek dizinleri belirtin; örnekteki yollar yer tutucudur:

```sh
python3 scripts/component_inventory.py \
  --npm-root /GERCEK/node_modules \
  --python-root /GERCEK/venv/lib/python3.X/site-packages
```

Birden fazla `--npm-root` ve `--python-root` verilebilir. Docker, farklı kullanıcı,
uv araç ortamı veya başka venv'ler varsa her birinin gerçek paket dizini ayrıca
incelenmelidir. Bulunamama veya okunamama güvenlik onayı sayılmaz. Paket adı ve
sürümü yalnız metadata beyanıdır; resmi paket kaynağı ayrıca doğrulanmalıdır.
PyPI'deki `agent-reach` adı resmi Agent Reach projesiyle özdeş kabul edilmez.
Rapor yalnız seçilen dosya yollarını, paket adlarını, sürümleri ve sabit durum
kodlarını içerir; metadata'daki diğer alanlar ve hata metinleri çıktıya konmaz.

## Upstream kararları — uygulanmadı

- RuFlo [GHSA-v68m-49gm-5hgw](https://github.com/ruvnet/ruflo/security/advisories/GHSA-v68m-49gm-5hgw),
  23.11.2026: `ruflo <3.80.1`; `@claude-flow/cli >=3.0.0-alpha.83, <3.80.1`;
  `claude-flow >=3.0.0-alpha.65, <3.80.1`. Advisory düzeltmesi 3.80.1.
  Güvenilmeyen checkout içinde CLI başlatmak update checker üzerinden kod
  çalıştırabilir. Sürüm tespiti için bu CLI'yı çalıştırmayın; metadata okuyun.
- OmniRoute [GHSA-hf57-cqmx-p4gr](https://github.com/cheaper-inference/OmniRoute/security/advisories/GHSA-hf57-cqmx-p4gr),
  03.09.2026: `<3.8.49`, düzeltme `3.8.49`. ACP custom-agent RCE;
  kurulu sürüm ve `requireLogin`/dış erişim birlikte incelenmeli.
- MCP-Scan'in eski deposu [Snyk Agent Scan'e](https://github.com/invariantlabs-ai/mcp-scan)
  yönleniyor. Eski komut ve çıktı formatına bağlı entegrasyonlar staging'de
  sınanmadan değiştirilmemeli.

Bu belge tarihli inceleme notudur; gelecekteki sürümler için güncel advisory
yeniden okunmalıdır. Hiçbir upstream paket sürümü bu değişiklikle yükseltilmedi.

## Doğrulama ve canlı kabul

Yerel doğrulama (tamamlandı): ayrı geçici test venv'ine depodaki `mcp==2.2.0`
kuruldu. 70 seçili testin tamamı geçti, atlanan test kalmadı. Gerçek SDK stdio
istemcisiyle el sıkışması, tam salt okunur araç kümesi, allowlist reddi ve geçersiz
limit reddi ayrıca geçti. Tekrarı: `python scripts/check_mcp_boundary.py`.
Python derleme ve `git diff --check` geçti. Bu, canlı veritabanı veya sunucudaki
paket sürümü doğrulaması değildir.

Canlıya alma öncesinde mevcut ayrı `venv-mcp` ortamında:

1. Kurulu SDK sürümünü metadata ile doğrulayın. Üretim venv'ine paket eklemeyin.
2. `venv-mcp/bin/python -m unittest tests.test_mcp_server tests.test_mcp_payload -v`.
   SDK testleri atlanıyorsa kabul etmeyin; import sorununu inceleyin.
3. Mevcut salt okunur `scripts/run_mcp_smoke.py` ile gerçek stdio el sıkışmasını
   ve allowlist davranışını doğrulayın. Bu kontrol burada çalıştırılmadı.
4. İstemcinin `kirpildi` ve `SORAMADIM` gösterimini kontrol edin; hata metni
   yerine `hata_kodu` kullanın.
5. Başarılı kabul ve yayın kararı sonrasında yalnız değişen dosyaları dağıtın;
   geri dönüş için önceki commit ve dosyaları saklayın.

Bu PR canlı dağıtım yapmaz, servis yeniden başlatmaz ve port/token ayarlarını
değiştirmez. Canlı kabul tamamlanmadan upstream açıkların kapatıldığı söylenemez.
