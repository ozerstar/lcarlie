"""Rakip tarama ajanı: TASK.md'deki görevi Jarvis'in ücretsiz araçlarıyla yapar ve Radar JSON'u yazar.

Neden ayrı ajan (29.10.2026): paket JARVIS_AGENT_CMD bekliyordu ama Jarvis'te sayfa okuyup alıntı
kopyalayan bir ajan yoktu. Jarvis'in rakip programı Gemini arama özetleri üretiyor; özet metni
"alıntı" olarak verilirse Radar'ın uydurma koruması (sayı alıntıda geçmeli) boşa düşer, çünkü
alıntıyı da model yazmış olur.

Burada sayfayı SUNUCU indirir; model yalnız o sayfanın metninden çıkarım yapar ve her alıntı
indirilen metinde birebir aranır. Sayfada geçmeyen alıntı, fiyat veya ürün adı atılır.

Bağımlılıklar dışarıdan verilir (test edilebilir):
  ara(soru)  -> (metin, ["başlık url", ...])   Gemini Google Search (program_baglantilari.grounded_arama)
  getir(url) -> (son_url, html)                 sunucudan HTTP GET
  uret(mesajlar, **kw) -> {"text": ...}         ücretsiz model yönlendiricisi (yerel_model.yonlendirici)
"""
import datetime as dt
import json
import re
import urllib.parse
import urllib.request

from .util import UA, html_to_text, iso, katla, now, number_in_text, valid_url

SAYFA_SINIRI = 9000       # modele giden sayfa metni (karakter); yerel modelin 8K bağlamına sığar
EN_FAZLA_BAYT = 2_000_000

# TASK.md "Ne aranacak" grupları; her gün sıradaki birkaç sorgu çalışır.
SORGULAR = [
    "Trendyol dermokozmetik krem fiyatı yüksekten düşüğe markalar",
    "Trendyol bitkisel bakım kremi premium markalar",
    "Trendyol intim bakım kremi markaları",
    "Trendyol gece kremi dermokozmetik yeni markalar",
    "yeni dermokozmetik markası Türkiye 2026",
    "son bir yılda kurulan Türk cilt bakım markaları",
    "doğal içerikli yüz kremi Türk markaları",
    "organik vegan cilt bakım markaları Türkiye",
    "bitkisel merhem balsam onarıcı krem markaları",
    "nasır kremi bitkisel marka",
    "rossmann.com.tr cilt bakım yeni markalar",
    "online eczane dermokozmetik yeni markalar",
    "Kore ithal dermokozmetik markaları Türkiye eczane",
]

SISTEM = (
    "Bir web sayfasının düz metnini alıp yalnız o metinde yazanı JSON olarak çıkarıyorsun. "
    "Tahmin etme, sayfada olmayan hiçbir şeyi yazma. Her 'alinti' alanı sayfa metninden HARFİ HARFİNE "
    "kopyalanmış kısa bir parça olmalı (en çok 120 karakter). Makyaj/renkli kozmetik ve ilaç markalarını yazma. "
    "Sayfa bir cilt bakım markası veya ürünü değilse {\"markalar\": []} döndür.")

SEMA = (
    '{"markalar": [{"marka": "Marka adı", "website": "https://... veya null", "instagram": "https://... veya null", '
    '"trendyol_url": "https://... veya null", "origin": "TR|KR|FR|... veya null", '
    '"tanitim": ["markayı anlatan alıntı"], '
    '"urunler": [{"ad": "ürün adı", "kategori": "yuz|vucut|bebek|gunes|sac|intim|dudak|agiz_dis|roll_on|sprey", '
    '"fiyat": 1450, "alinti": "fiyatın geçtiği alıntı, ör. Onarıcı Balsam 50 ml 1.450 TL"}], '
    '"kanallar": [{"kanal": "eczane|rossmann|gratis|watsons|trendyol|hepsiburada|kendi_sitesi", "alinti": "..."}], '
    '"yorum_sayisi": {"deger": 1234, "alinti": "1.234 Değerlendirme"}}]}')


def _bosluk(s):
    return re.sub(r"\s+", " ", katla(s or "")).strip()


def alinti_var(alinti, metin):
    """Alıntı sayfa metninde (büyük/küçük harf ve boşluk farkı gözetmeden) birebir geçiyor mu?"""
    a = _bosluk(alinti)
    return len(a) >= 3 and a in _bosluk(metin)


def http_getir(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ham = r.read(EN_FAZLA_BAYT)
        return r.geturl(), ham.decode(r.headers.get_content_charset() or "utf-8", "replace")


_LD = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_FIYAT = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:[.,]\d+)?\s*(?:TL|₺|TRY)")


def _ld_urunleri(d):
    if isinstance(d, list):
        for x in d:
            yield from _ld_urunleri(x)
    elif isinstance(d, dict):
        tip = d.get("@type")
        if tip == "Product" or (isinstance(tip, list) and "Product" in tip):
            yield d
        for k in ("@graph", "itemListElement", "item", "mainEntity"):
            if k in d:
                yield from _ld_urunleri(d[k])


def yapisal_veri(ham):
    """Sayfanın kendi JSON-LD ürün verisini düz satırlara çevirir.

    Rossmann gibi siteler ürün listesini JavaScript ile çiziyor; düz HTML'de fiyat yok
    (29.10.2026 ölçüldü). Ürün sayfalarının çoğu ise schema.org Product verisi taşır.
    Bu satırlar sayfadan gelir; alıntı doğrulaması bunlara karşı da yapılır.
    """
    satirlar = []
    for blok in _LD.findall(ham or ""):
        try:
            veri = json.loads(blok.strip())
        except ValueError:
            continue
        for u in _ld_urunleri(veri):
            marka = u.get("brand")
            marka = marka.get("name") if isinstance(marka, dict) else marka
            teklifler = u.get("offers") or {}
            teklifler = teklifler if isinstance(teklifler, list) else [teklifler]
            for t in teklifler[:3] or [{}]:
                fiyat = t.get("price") or t.get("lowPrice")
                satirlar.append(" | ".join(x for x in (
                    f"Ürün: {u.get('name')}" if u.get("name") else "",
                    f"Marka: {marka}" if marka else "",
                    f"Fiyat: {fiyat} {t.get('priceCurrency') or ''}".strip() if fiyat else "") if x))
    return "\n".join(dict.fromkeys(s for s in satirlar if s))


def odak(metin, sinir=SAYFA_SINIRI):
    """Uzun sayfada menü yerine fiyatların en yoğun olduğu bölümü seçer."""
    if len(metin) <= sinir:
        return metin
    konumlar = [m.start() for m in _FIYAT.finditer(metin)]
    if not konumlar:
        return metin[:sinir]
    en_iyi, bas = 0, 0
    j = 0
    for i, k in enumerate(konumlar):
        while konumlar[j] < k - sinir + 400:
            j += 1
        if i - j + 1 > en_iyi:
            en_iyi, bas = i - j + 1, max(0, konumlar[j] - 400)
    return metin[bas:bas + sinir]


def fiyat_bitisik(metin):
    """Tarayıcı metninde '429,\\n00 TL' gibi bölünen fiyatları birleştirir (Rossmann, 29.10.2026)."""
    return re.sub(r"(\d),\s+(\d{2})(?=\s*(?:TL|₺)\b|\s)", r"\1,\2", metin)


def tarayici_getir(url, bekle_ms=6000):
    """Başsız Chromium ile sayfayı çizer (Playwright). Gizleme/taklit yok; 403 veren site engellenmiş sayılır."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            s = b.new_page(locale="tr-TR", user_agent=UA)
            yanit = s.goto(url, wait_until="domcontentloaded", timeout=45000)
            if yanit is not None and yanit.status >= 400:
                raise OSError(f"HTTP {yanit.status} (tarayıcı)")
            s.wait_for_timeout(bekle_ms)
            for _ in range(6):   # tembel yüklenen ürün kartları (Gratis) için aşağı kaydır
                s.mouse.wheel(0, 2500)
                s.wait_for_timeout(800)
            return s.url, s.content()
        finally:
            b.close()


def akilli_getir(url, duz=http_getir, tarayici=tarayici_getir):
    """Önce düz HTTP; sayfada fiyat da JSON-LD de yoksa (JS ile çiziliyor) tarayıcıyla açar.

    29.10.2026 ölçüm: Rossmann düz HTML'de 0 fiyat, tarayıcıda 48 fiyat; eczane sitesi düz HTML'de JSON-LD.
    """
    son, ham = duz(url)
    # Ürün fiyatı kuruşlu yazılır ("175,00"); "2000 TL ve üzeri kargo bedava" gibi afiş metni sayılmaz
    # (29.10.2026: Rossmann düz HTML'deki afiş metinleri yüzünden tarayıcı hiç açılmamıştı).
    kurus = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", html_to_text(ham))
    if yapisal_veri(ham) or len(kurus) >= 3:
        return son, ham
    try:
        return tarayici(url)
    except ImportError:
        return son, ham   # sunucuda Playwright yoksa düz sayfa ile devam
    except OSError:
        raise             # tarayıcıda da HTTP 4xx/5xx: site engelliyor, kaynak sağlığına yazılsın
    except Exception:  # noqa: BLE001
        # Tarayıcı açılamadıysa (30.10.2026 sunucuda TasksMax=32 iken Chromium çöktü) düz sayfayla devam:
        # JSON-LD/model yolu yine çalışır, yalnız JS ile çizilen fiyatlar kaçar.
        return son, ham


_SADE_FIYAT = re.compile(r"^(?:₺\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(?:\s*(?:TL|₺))?$")
_GURULTU = re.compile(r"^(?:TL|₺|Sepete Ekle|Stokta Yok|Tükendi|Yeni|İndirim|%\s?\d+.*|\d+)$", re.I)


def slug(s):
    s = katla(s)
    for a, b in (("ç", "c"), ("ğ", "g"), ("ö", "o"), ("ş", "s"), ("ü", "u"), ("â", "a"), ("é", "e"), ("&", "and")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def liste_cikar(metin, markalar, url, zaman=None, en_cok=80):
    """Ürün LİSTESİ sayfasından (Rossmann vb.) modelsiz çıkarım.

    Desen (29.10.2026, Rossmann gerçek sayfası): [marka][ürün adı][TL][175,00][TL]...
    Her fiyat satırından geriye gidilir: gürültü satırları atlanır, ürün adı ve markası alınır.
    Marka yalnız bilinen marka sözlüğündeyse (eczane site haritası + Radar markaları) kabul edilir.
    Alıntı, sayfa metninin marka satırından fiyat satırına kadar olan BİREBİR parçasıdır.
    """
    L = metin.splitlines()
    ts = iso(zaman or now())
    bulunan, gorulen = {}, set()
    for i, satir in enumerate(L):
        m = _SADE_FIYAT.match(satir.strip())
        if not m:
            continue
        j = i - 1
        while j >= 0 and _GURULTU.match(L[j].strip()):
            j -= 1
        if j < 1:
            continue
        urun, marka = L[j].strip(), L[j - 1].strip()
        if slug(marka) not in markalar or len(urun) < 4 or (marka, urun) in gorulen:
            continue
        gorulen.add((marka, urun))
        alinti = "\n".join(L[j - 1:i + 1])
        fiyat = float(m.group(1).replace(".", "").replace(",", "."))
        b = bulunan.setdefault(marka, {"name": marka, "texts": [], "observations": []})
        b["texts"].append(urun)
        b["observations"] += [
            {"kind": "product", "product": urun, "source_url": url, "fetched_at": ts},
            {"kind": "price", "product": urun, "value": fiyat, "source_url": url, "fetched_at": ts,
             "excerpt": " ".join(alinti.split())[:300]}]
        if len(gorulen) >= en_cok:
            break
    return list(bulunan.values())


def json_ayikla(metin):
    bas, son = (metin or "").find("{"), (metin or "").rfind("}")
    if bas < 0:
        raise ValueError("JSON yok")
    try:
        return json.loads(metin[bas:son + 1])
    except ValueError:
        onarilan = kesik_json_onar(metin[bas:])
        if onarilan is None:
            raise
        return onarilan


def kesik_json_onar(t):
    """Çıktı sınırında yarıda kesilmiş JSON'u son tam öğeye kadar kurtarır.

    Jarvis is_uretici._kesik_json_onar ile aynı yöntem; 29.10.2026 Rossmann sayfasında yerel 4B model
    JSON'u 5.085. karakterde kesti.
    """
    for kes in [i for i, c in enumerate(t) if c in ",}]"][::-1][:400]:
        parca = t[:kes] if t[kes] == "," else t[:kes + 1]
        yigin, icerde, kacis = [], False, False
        for c in parca:
            if icerde:
                if kacis:
                    kacis = False
                elif c == "\\":
                    kacis = True
                elif c == '"':
                    icerde = False
            elif c == '"':
                icerde = True
            elif c in "{[":
                yigin.append("}" if c == "{" else "]")
            elif c in "}]":
                if not yigin:
                    break
                yigin.pop()
        if icerde:
            continue
        try:
            v = json.loads(parca + "".join(reversed(yigin)))
        except ValueError:
            continue
        if isinstance(v, dict) and v:
            return v
    return None


def _alan(url):
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


_LD_SATIR = re.compile(r"^Ürün: (?P<urun>.+?) \| Marka: (?P<marka>.+?)(?: \| Fiyat: (?P<fiyat>[\d.]+) (?P<pb>\w+))?$")


def ld_markalari(yapisal, son_url, ts):
    """yapisal_veri() satırlarından Radar marka kayıtları; alıntı = satırın kendisi."""
    out = {}
    for s in (yapisal or "").splitlines():
        m = _LD_SATIR.match(s)
        if not m:
            continue
        b = out.setdefault(m["marka"], {"name": m["marka"], "texts": [], "observations": []})
        if m["urun"] in b["texts"]:
            continue
        b["texts"].append(m["urun"])
        b["observations"].append({"kind": "product", "product": m["urun"], "source_url": son_url, "fetched_at": ts})
        if m["fiyat"] and (m["pb"] or "").upper() in ("TRY", "TL"):
            b["observations"].append({"kind": "price", "product": m["urun"], "value": float(m["fiyat"]),
                                      "source_url": son_url, "fetched_at": ts, "excerpt": s})
    return list(out.values())


def sayfa_cikar(url, getir, uret, zaman=None, markalar=None):
    """Bir sayfayı indirir, modelden çıkarım ister, alıntıları sayfaya karşı doğrular.

    Döner: (markalar, kaynak_durumu, red_sayisi)
    """
    zaman = zaman or now()
    try:
        son_url, ham = getir(url)
    except Exception as e:  # noqa: BLE001 -- açılmayan sayfa sessizce atlanmaz, kaynak sağlığına yazılır
        return [], {"source": _alan(url) or url, "ok": False, "error": str(e)[:200]}, 0
    yapisal = yapisal_veri(ham)
    duz = fiyat_bitisik(html_to_text(ham))
    metin = (yapisal + "\n" + duz) if yapisal else duz   # doğrulama tüm sayfa metnine karşı
    durum = {"source": _alan(son_url), "ok": True}
    if len(metin) < 200:
        return [], dict(durum, ok=False, error="sayfa metni boş (JS ile yükleniyor olabilir)"), 0
    # 1) Sayfanın kendi JSON-LD ürün verisi varsa model kullanılmaz (29.10.2026: eczane, Gratis, marka siteleri).
    ld = ld_markalari(yapisal, son_url, iso(zaman))
    if ld:
        return ld, durum, 0
    # 2) Ürün listesi sayfası (Rossmann): bilinen marka sözlüğüyle modelsiz çıkarım.
    if markalar:
        liste = liste_cikar(duz, markalar, son_url, zaman)
        if liste:
            return liste, durum, 0
    # 3) Son çare: model (yerel 4B model uzun listede JSON'u kesebiliyor; kesik JSON onarılır).
    goster = (yapisal[:2000] + "\n" + odak(duz, SAYFA_SINIRI - min(len(yapisal), 2000))) if yapisal else odak(duz)
    mesajlar = [{"role": "system", "content": SISTEM},
                {"role": "user", "content": f"Şema:\n{SEMA}\n\nSayfa: {son_url}\n<veri>\n{goster}\n</veri>"}]
    try:
        cikti = json_ayikla(uret(mesajlar, max_tokens=1800, is_anahtari="radar-cikar")["text"])
    except Exception as e:  # noqa: BLE001
        return [], dict(durum, ok=False, error=f"model çıktısı okunamadı: {str(e)[:120]}"), 0
    ts = iso(zaman)
    markalar, red = [], 0
    for m in cikti.get("markalar") or []:
        ad = (m.get("marka") or "").strip()
        if not ad or not alinti_var(ad, metin):
            red += 1
            continue
        obs = []
        for u in m.get("urunler") or []:
            uad = (u.get("ad") or "").strip()
            if not uad or not alinti_var(uad, metin):
                red += 1
                continue
            obs.append({"kind": "product", "product": uad, "category": u.get("kategori"),
                        "source_url": son_url, "fetched_at": ts})
            al = u.get("alinti") or ""
            if u.get("fiyat") is not None and alinti_var(al, metin) and _sayi(u["fiyat"], al):
                obs.append({"kind": "price", "product": uad, "category": u.get("kategori"), "value": float(u["fiyat"]),
                            "source_url": son_url, "fetched_at": ts, "excerpt": al})
            elif u.get("fiyat") is not None:
                red += 1
        for k in m.get("kanallar") or []:
            if k.get("kanal") and alinti_var(k.get("alinti"), metin):
                obs.append({"kind": "channel", "value": k["kanal"], "source_url": son_url, "fetched_at": ts})
        ys = m.get("yorum_sayisi") or {}
        if ys.get("deger") is not None and alinti_var(ys.get("alinti"), metin) and _sayi(ys["deger"], ys["alinti"]):
            obs.append({"kind": "review_count", "value": float(ys["deger"]), "source_url": son_url,
                        "fetched_at": ts, "excerpt": ys["alinti"]})
        tanitim = [t for t in (m.get("tanitim") or []) if alinti_var(t, metin)]
        b = {"name": ad, "texts": tanitim, "observations": obs, "origin": m.get("origin")}
        for alan in ("website", "instagram", "trendyol_url"):
            if valid_url(m.get(alan)):
                b[alan] = m[alan]
        if "trendyol.com" in son_url and not b.get("trendyol_url"):
            b["trendyol_url"] = son_url
        markalar.append(b)
    return markalar, durum, red


def _sayi(deger, alinti):
    try:
        return number_in_text(float(deger), alinti)
    except (TypeError, ValueError):
        return False


def _birlestir(hepsi):
    """Aynı marka birden çok sayfadan gelirse tek kayıtta toplanır."""
    out = {}
    for b in hepsi:
        k = katla(b["name"])
        if k not in out:
            out[k] = b
            continue
        hedef = out[k]
        hedef["observations"] += b["observations"]
        hedef["texts"] += [t for t in b["texts"] if t not in hedef["texts"]]
        for alan in ("website", "instagram", "trendyol_url", "origin"):
            if not hedef.get(alan) and b.get(alan):
                hedef[alan] = b[alan]
    return list(out.values())


def gunun_sorgulari(adet, gun=None):
    gun = gun or now().date()
    bas = (gun.toordinal() * adet) % len(SORGULAR)
    return [SORGULAR[(bas + i) % len(SORGULAR)] for i in range(adet)]


def _urller(ara, sorgu):
    _, kaynaklar = ara(f"{sorgu}. Türkiye'de satılan bu tanıma uyan cilt bakım markalarının ürün veya mağaza "
                       f"sayfalarını bul; her marka için bir sayfa yeterli.")
    out = []
    for k in kaynaklar:
        u = k.split()[-1] if k else ""
        if valid_url(u):
            out.append(u)
    return out


# Arama motoruna bırakılmayan, her taramada bakılan liste sayfaları (robots.txt izin veriyor, 29.10.2026).
SABIT_SAYFALAR = ["https://www.rossmann.com.tr/cilt-bakimi", "https://www.rossmann.com.tr/anne-bebek/bebek-bakim-kremleri"]


def calistir(mod, ara, getir, uret, teyit=None, izlenen=None, sorgu_adedi=4, sayfa_siniri=12, markalar=None):
    """mod: tarama | teyit. Radar'ın ingest ettiği JSON'u döndürür.

    markalar: bilinen marka slug'ları (eczane/Gratis site haritası) -> liste sayfalarında modelsiz çıkarım.
    """
    durumlar, hepsi, red, ziyaret = [], [], 0, set()

    def isle(url):
        nonlocal red
        if url in ziyaret or len(ziyaret) >= sayfa_siniri:
            return
        ziyaret.add(url)
        m, d, r = sayfa_cikar(url, getir, uret, markalar=markalar)
        durumlar.append(d)
        hepsi.extend(m)
        red += r

    if mod == "teyit":
        for satir in teyit or []:
            if valid_url(satir.get("source_url")):
                isle(satir["source_url"])
        # Teyitte yalnız istenen markalar kalır (TASK.md: "başka marka ekleme").
        istenen = {katla(s.get("brand") or "") for s in teyit or []}
        hepsi = [b for b in hepsi if katla(b["name"]) in istenen]
    else:
        for b in izlenen or []:
            for alan in ("trendyol_url", "website"):
                if valid_url(b.get(alan)):
                    isle(b[alan])
                    break
        for u in SABIT_SAYFALAR:
            isle(u)
        for sorgu in gunun_sorgulari(sorgu_adedi):
            try:
                for u in _urller(ara, sorgu):
                    isle(u)
            except Exception as e:  # noqa: BLE001
                durumlar.append({"source": "gemini-arama", "ok": False, "error": f"{sorgu}: {str(e)[:150]}"})
    return {"source": f"jarvis-{mod}", "source_status": durumlar, "brands": _birlestir(hepsi),
            "ajan": {"sayfa": len(ziyaret), "dogrulanamayan": red, "zaman": iso(now())}}
