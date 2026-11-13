"""Jarvis sohbet ajanı: Claude mesajı olduğu gibi okur, araçlarla veriye
bakar, gerekirse web'de araştırır ve cevabı yazarken akıtır.

NEDEN VAR (12.11.2026, sahip): "çok yavaş, ne cevap verdiği belli değil,
komple yazabilmesi, düşünebilmesi ve araştırabilmesi gerekiyor."
Eski yol mesajı anahtar kelimelerle bir kalıba sokup ya hazır cümle
dolduruyor ya da modele tek seferlik bir kanıt paketi veriyordu; model
veri isteyemiyor, ikinci adım atamıyor, araştıramıyordu.

🔴 SINIR: araçların HEPSİ SALT OKUNUR. Fiyat, reklam, mesaj, ürün -- hiçbir
   şey buradan değiştirilemez; eylem istekleri chat.stream'de bu ajana hiç
   gelmez (ACTION_REQUEST güvenlik duvarına gider). Şirket verisi yalnız
   CompanyMemory'nin izinli sorgularından, ai_reader rolüyle okunur.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

ACIK = os.environ.get("JARVIS_AJAN", "1") != "0"
MODEL = os.environ.get("JARVIS_AJAN_MODEL", "claude-opus-5-5")
# Sohbet hiz ister: dusuk efor daha az ve toplu arac cagrisi, kisa onsoz.
EFOR = os.environ.get("JARVIS_AJAN_EFOR", "low")
# Reddetmede yedek modele gecis (server-side fallback). 12.11.2026 olculdu:
# acikken ilk kelime 6,9 sn, kapaliyken 0,8 sn -- sunucu ciktiyi biriktiriyor.
# Sohbetin ana sikayeti hiz oldugu icin varsayilan KAPALI; ret olursa ajan
# "yanitlayamiyorum" der. Acmak icin JARVIS_AJAN_YEDEK_MODEL=1.
YEDEK_MODEL = os.environ.get("JARVIS_AJAN_YEDEK_MODEL", "0") == "1"
EN_FAZLA_TUR = 6
ARAC_CIKTI_SINIRI = 14000
GECMIS_TUR = 6
KAYIT = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")) / "ajan.jsonl"


class AjanKullanilamaz(RuntimeError):
    """Ajan cevap uretmeye BASLAYAMADI; cagiran eski yola donebilir."""


# Model yalniz bu sorgulari secebilir (enum). Ic sistem sorgulari
# (action_contract, provenance, model_kademe ...) bilerek disarida.
SORGULAR: dict[str, str] = {
    "operations_marketplace_orders": "Tüm kanalların siparişleri (Wix, Trendyol, Idefix, n11...), 2 dakikada bir taranır: kanal, zaman, tutar (KDV dahil), durum",
    "operations_channel_health": "Satış kanallarının bağlantı durumu (çalışıyor / bağlı değil / hata)",
    "sales_orders": "Wix sitesi siparişleri, günde bir (08:30) yüklenir: ödeme, net ciro, doğrulanmış/beyan ciro",
    "sales_items": "Wix'te satılan ürün kalemleri: ürün, adet, net ciro, maliyet, brüt marj",
    "satis_kohort": "Satış kohortları (müşterilerin tekrar alımı)",
    "satis_yaklasim": "Satış yaklaşımı / kanal bazlı satış özeti",
    "operations_shipments": "Kargo gönderileri, durumları ve alarmlar",
    "advertising_performance": "Meta reklam performansı: kampanya, reklam, harcama, CTR, pencere (gün)",
    "advertising_spend": "Reklam harcaması",
    "kreatif_performans": "Reklam kreatiflerinin performansı",
    "creative_coverage": "Hangi ürün/mesaj için kreatif var, hangisi eksik",
    "crm_unanswered": "Cevapsız müşteri konuşmaları ve bekleme süreleri",
    "crm_customers": "Müşteri kayıtları (kişisel veri içermez)",
    "customer_voice": "Müşteri sesi: sık gelen soru ve şikâyetler",
    "ecommerce_profitability": "Ürün bazında ciro, maliyet ve brüt marj",
    "ecommerce_price": "Ürün fiyatları (site)",
    "platform_fiyat_matrisi": "Ürün × pazaryeri fiyat matrisi ve komisyon",
    "ecommerce_funnel": "Site dönüşüm hunisi (ziyaret → sepet → ödeme)",
    "urun_karti": "Ürün kartları: ad, açıklama, içerik",
    "urun_bilgi": "Ürün bilgileri",
    "urun_seo": "Ürün SEO alanları",
    "sayfa_olcum": "Site sayfa ölçümleri (hız, içerik)",
    "financial": "Finans özeti",
    "financial_cash": "Nakit durumu",
    "company_dashboard": "Yönetim panosu özeti",
    "gunluk_brief": "Günlük yönetim brifi",
    "agenda": "Şirket gündemi: açık sorular ve öncelikleri",
    "open_work": "Açık işler listesi",
    "departments": "Departmanlar",
    "market_research": "Pazar araştırması notları",
    "basin_bahsi": "Basında / webde marka bahsi",
    "content_performance": "İçerik (Instagram vb.) performansı",
    "ig_gunluk_paket": "Günlük Instagram içerik paketi",
    "tasarim_isleri": "Tasarım işleri",
    "data_quality": "Veri kalitesi sorunları",
}

ARACLAR: list[dict[str, Any]] = [
    {
        "name": "sirket_verisi",
        "description": "Şirketin canlı veritabanından hazır bir sorguyu çalıştırır (salt okunur). "
                       "Rakam, liste, durum gereken her şirket sorusunda kullan. Sorgular:\n"
                       + "\n".join(f"- {ad}: {aciklama}" for ad, aciklama in SORGULAR.items()),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"sorgu": {"type": "string", "enum": sorted(SORGULAR)}},
            "required": ["sorgu"],
        },
    },
    {
        "name": "satis_ozeti",
        "description": "Satış/sipariş sorusunu hazır hesapla cevaplar: dönem (bugün, dün, bu hafta, "
                       "geçen hafta, bu ay, geçen ay, son N gün) ve kanal (Trendyol, Idefix, "
                       "Hepsiburada, n11, Wix) anlar. Sipariş sayısı/ciro sorularında önce bunu dene.",
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"soru": {"type": "string", "description": "Türkçe soru, ör. 'trendyol bu ay kaç sipariş'"}},
            "required": ["soru"],
        },
    },
    {
        "name": "bekleyen_onaylar",
        "description": "Sahibin onayını bekleyen öneri sayısı.",
        "eager_input_streaming": True,
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "sirket_bilgisi",
        "description": "Şirketin doğrulanmış bilgi deposu: ürünler ve içerikleri, fiyat kuralları, "
                       "marka dili, iddia (mevzuat) kuralları, kapanmış kararlar.",
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"konu": {"type": "string"}},
            "required": ["konu"],
        },
    },
    {
        "name": "web_arastir",
        "description": "Google araması ile web araştırması: pazar, rakip, fiyat, mevzuat, haber, "
                       "genel bilgi. Özet ve kaynak bağlantıları döner; cevapta kaynakları belirt.",
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"soru": {"type": "string"}},
            "required": ["soru"],
        },
    },
]

ASAMA = {
    "sirket_verisi": lambda g: "Şirket verisine bakıyorum: " + SORGULAR.get(str(g.get("sorgu")), "").split(":")[0],
    "satis_ozeti": lambda g: "Satış rakamlarını topluyorum",
    "bekleyen_onaylar": lambda g: "Bekleyen onaylara bakıyorum",
    "sirket_bilgisi": lambda g: "Şirket bilgisini okuyorum: " + str(g.get("konu") or "")[:40],
    "web_arastir": lambda g: "Web'de araştırıyorum: " + str(g.get("soru") or "")[:50],
}

SISTEM = """Sen Jarvis'sin: L'CARLIÉ şirketinin yönetim asistanısın. L'CARLIÉ Türk doğal kozmetik markası; kendi Wix sitesi var ve Trendyol, Idefix, n11, Hepsiburada'da satıyor. Konuştuğun kişi şirket sahibi.

Nasıl çalışırsın:
- Sahip telefondan hızlı yazar: harf hatası, eksik Türkçe karakter (ı/i, s/ş, g/ğ) olur. Niyeti anla; yazım hatasından hiç bahsetme, düzeltme isteme.
- Şirketle ilgili her rakamı, durumu ve tarihi araçlardan al. Araçlarda olmayan bir şeyi uydurma. Bulamadıysan neye baktığını ve neyin eksik olduğunu tek cümleyle söyle.
- Gerekirse birden fazla araç kullan; birbirinden bağımsız sorguları aynı anda iste.
- Şirket dışı ya da güncel bilgi (pazar, rakip, mevzuat, haber, genel bilgi) için web_arastir kullan ve kullandığın kaynakları cevabın sonunda kısaca yaz.
- Hiçbir şeyi değiştiremezsin: fiyat, reklam, ürün, müşteriye mesaj. Böyle bir istek gelirse yapmadığını açıkça söyle, ne yapılabileceğini öner ve Jarvis panelinden onaya gönderilebileceğini belirt. Asla "yaptım", "gönderdim", "iletildi" deme.
- Finansal hesaplarda KDV temeli, iadelerin cirodan düşülüp düşülmediği veya gider kapsamı belirsizse kalan tutarı katkı, marj ya da net kâr diye etiketleme. Önce bu ölçünün hesaplanamadığını söyle. İstenirse yalnız açık varsayımlarla “koşullu aritmetik örnek (gerçekleşmiş katkı/kâr değildir)” ver; varsayımları rakamdan önce belirt. ROAS hesabında atıf penceresi bilinmiyorsa oranı yalnız verilen atıflı ciro/harcama oranı olarak sun; nedensellik veya bütçe artırma sonucu çıkarma. Yalnız KDV/iade bilgisinin tamamlanmasının net kâr için yeterli olduğunu söyleme; tüm ilgili gelir, maliyet, komisyon, genel gider ve vergi kapsamı da doğrulanmalıdır.
- Müşteriye gidecek bir metin yazarsan tıbbi iddia kullanma (tedavi eder, iyileştirir, hastalık adı); kozmetik dil kullan.

Cevap biçimi:
- Türkçe. İlk cümle doğrudan cevap. Kısa ve net; gerekiyorsa birkaç madde.
- Başlık, tekrar, "umarım yardımcı olur" gibi dolgu yok.
- Tutarları TL ile yaz; verinin KDV dahil mi hariç mi olduğu biliniyorsa belirt."""


# ----------------------------------------------------------------- araclar
def _kisalt(metin: str) -> str:
    return metin if len(metin) <= ARAC_CIKTI_SINIRI else metin[:ARAC_CIKTI_SINIRI] + "\n[... kısaltıldı]"


def _sirket_verisi(girdi: dict, memory: Any) -> str:
    ad = girdi.get("sorgu")
    if ad not in SORGULAR:
        raise ValueError("bilinmeyen sorgu")
    kayitlar = memory._fetch(ad).records
    if not kayitlar:
        return f"{ad}: kayıt yok (sorgu çalıştı, sonuç boş)."
    return _kisalt(f"{ad}: {len(kayitlar)} kayıt\n"
                   + "\n".join(json.dumps(k, ensure_ascii=False, default=str) for k in kayitlar))


def _satis_ozeti(girdi: dict, memory: Any) -> str:
    import conversation  # gec import: conversation bu modulu yuklemeden calisir
    soru = str(girdi.get("soru") or "")
    return conversation._sales_answer(soru, memory._fetch("sales_orders").records, memory)


def _bekleyen_onaylar(girdi: dict, memory: Any) -> str:
    satir = (memory.get_system_status().records or [{}])[0]
    return (f"{int(satir.get('pending_actions') or 0)} öneri sahibin onayını bekliyor "
            "(panelde Onaylar ekranı; yeni öneriler WhatsApp'a da düğmeli gelir).")


def _sirket_bilgisi(girdi: dict, memory: Any) -> str:
    from jarvis.company_knowledge import shared
    metin = shared().context(str(girdi.get("konu") or ""), internal_ok=True)
    return _kisalt(metin) if metin else "Bilgi deposunda bu konuda belge bulunamadı."


def _web_arastir(girdi: dict, memory: Any) -> str:
    """Gemini Google Search grounding: ozet + cozulmus kaynak adresleri.

    research_sources._gemini_search bilerek modelin metnini KULLANMAZ (orasi
    bir arama dizini). Sohbette sahip bir ozet + kaynak istiyor; ozet Claude'a
    "web ozeti" olarak verilir ve kaynaklar cevapta belirtilir.
    """
    from jarvis import providers, research_sources as rs
    soru = str(girdi.get("soru") or "").strip()
    if not soru:
        raise ValueError("soru bos")
    anahtar = (providers.load_env().get("GEMINI_API_KEY") or "").strip()
    if not anahtar:
        return "Web araştırması yapılamadı: arama anahtarı tanımlı değil."
    adres = (rs.GEMINI_ENDPOINT.format(model=rs.GEMINI_SEARCH_MODEL)
             + "?key=" + urllib.parse.quote(anahtar, safe=""))
    govde = {"contents": [{"parts": [{"text": soru + "\n\nTürkçe, tarih ve rakamlarla, kısa özetle."}]}],
             "tools": [{"google_search": {}}]}
    istek = urllib.request.Request(adres, data=json.dumps(govde).encode("utf-8"),
                                   headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=rs.GEMINI_TIMEOUT) as yanit:
            veri = json.loads(yanit.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as hata:
        return f"Web araştırması başarısız (HTTP {hata.code})."   # anahtar metne sizmasin
    except (urllib.error.URLError, OSError, ValueError):
        return "Web araştırması başarısız (bağlantı)."
    aday = (veri.get("candidates") or [{}])[0]
    ozet = "".join(p.get("text", "") for p in (aday.get("content") or {}).get("parts") or [])
    parcalar = ((aday.get("groundingMetadata") or {}).get("groundingChunks") or [])[:6]
    with ThreadPoolExecutor(max_workers=max(1, len(parcalar))) as havuz:
        adresler = list(havuz.map(lambda p: rs._resolve_redirect(str((p.get("web") or {}).get("uri") or "")),
                                  parcalar))
    kaynaklar = [f"- {(p.get('web') or {}).get('title') or 'kaynak'}: {a}"
                 for p, a in zip(parcalar, adresler, strict=True) if a]
    return _kisalt("WEB ÖZETİ:\n" + (ozet.strip() or "(özet yok)")
                   + "\n\nKAYNAKLAR:\n" + ("\n".join(kaynaklar) or "(kaynak çözülemedi)"))


CALISTIRICI = {"sirket_verisi": _sirket_verisi, "satis_ozeti": _satis_ozeti,
               "bekleyen_onaylar": _bekleyen_onaylar, "sirket_bilgisi": _sirket_bilgisi,
               "web_arastir": _web_arastir}


def gecerli_girdi(ad: str, girdi: Any) -> bool:
    """eager_input_streaming ile sunucu girdiyi dogrulamaz; burada dogrulanir."""
    if not isinstance(girdi, dict):
        return False
    if ad == "sirket_verisi":
        return girdi.get("sorgu") in SORGULAR
    if ad == "bekleyen_onaylar":
        return True
    alan = {"satis_ozeti": "soru", "sirket_bilgisi": "konu", "web_arastir": "soru"}.get(ad)
    return bool(alan) and isinstance(girdi.get(alan), str) and bool(girdi[alan].strip())


def arac_calistir(blok: Any, memory: Any) -> dict[str, Any]:
    if blok.name not in CALISTIRICI or not gecerli_girdi(blok.name, blok.input):
        return {"type": "tool_result", "tool_use_id": blok.id, "is_error": True,
                "content": json.dumps({"INVALID_JSON": json.dumps(blok.input, default=str)})}
    try:
        return {"type": "tool_result", "tool_use_id": blok.id,
                "content": CALISTIRICI[blok.name](blok.input, memory)}
    except Exception as hata:  # noqa: BLE001 - arac hatasi modele soylenir, sohbet durmaz
        return {"type": "tool_result", "tool_use_id": blok.id, "is_error": True,
                "content": f"{blok.name} çalışmadı: {type(hata).__name__}: {str(hata)[:160]}"}


# ----------------------------------------------------------------- gecmis
def gecmis_mesajlar(gecmis: list[dict[str, str]], soru: str) -> list[dict[str, Any]]:
    """Kullanici/asistan sirasi garanti, ilk mesaj kullanici, son mesaj bu soru."""
    mesajlar: list[dict[str, Any]] = []
    for m in gecmis:
        rol, icerik = m.get("role"), str(m.get("content") or "").strip()
        if rol not in ("user", "assistant") or not icerik:
            continue
        if not mesajlar and rol != "user":
            continue
        if mesajlar and mesajlar[-1]["role"] == rol:
            mesajlar[-1]["content"] += "\n\n" + icerik
        else:
            mesajlar.append({"role": rol, "content": icerik})
    if mesajlar and mesajlar[-1]["role"] == "user":
        mesajlar.pop()           # cevapsiz kalmis eski soru: yeni soruyla karismasin
    mesajlar.append({"role": "user", "content": soru})
    return mesajlar


# ----------------------------------------------------------------- dongu
def _istemci():
    try:
        import anthropic
    except ImportError:
        raise AjanKullanilamaz("anthropic paketi kurulu degil") from None
    from jarvis import providers
    anahtar = (providers.load_env().get("ANTHROPIC_API_KEY") or "").strip()  # env'de CRLF var
    if not anahtar:
        raise AjanKullanilamaz("ANTHROPIC_API_KEY yok")
    return anthropic, anthropic.Anthropic(api_key=anahtar, timeout=90.0, max_retries=1)


def _kaydet(kayit: dict[str, Any]) -> None:
    try:
        with KAYIT.open("a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except OSError:
        pass


def stream(soru: str, memory: Any, gecmis: list[dict[str, str]] | None = None) -> Iterator[dict[str, Any]]:
    """{"type": "stage"|"token"|"done"} cerceveleri uretir (chat.stream ile ayni protokol).

    Hicbir sey uretilmeden once hata olursa AjanKullanilamaz firlatir; cagiran
    eski yola doner. Uretim basladiktan sonraki hata cevabin sonuna yazilir.
    """
    baslangic = time.perf_counter()
    # Durum cercevesi istemci kurulumu gecikse de hemen gorunur.
    yield {"type": "stage", "label": "Düşünüyorum"}
    anthropic, istemci = _istemci()
    # Ekran ilk saniyede bos kalmasin: arac + dusunme turu 2-4 sn surer.
    # Saat de verilir: 12.11 duman testinde ajan "son kontrol 02:11" kaydini
    # (saat 02:12'ydi) "tarama durmus olabilir" diye yanlis alarma cevirdi.
    simdi = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
    sistem = SISTEM + f"\n\nŞu an: {simdi} (Türkiye saati)."
    mesajlar = gecmis_mesajlar(gecmis or [], soru)
    metin: list[str] = []
    araclar: list[str] = []
    cagri = 0
    girdi_token = cikti_token = 0
    uretti = False
    hata_notu = ""
    akis_olcumleri: list[dict[str, Any]] = []
    ilk_metin_ms = None
    try:
        for _tur in range(EN_FAZLA_TUR):
            cagri += 1
            json_denemesi = 0
            while True:
                try:
                    yedek = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
                             if YEDEK_MODEL else {})
                    akis_baslangic = time.perf_counter()
                    olcum = {"tur": cagri, "deneme": json_denemesi + 1, "ilk_olay_ms": None,
                             "ilk_metin_ms": None, "son_metin_ms": None, "metin_parcasi": 0}
                    akis_olcumleri.append(olcum)
                    with istemci.beta.messages.stream(
                        model=MODEL, max_tokens=16000, system=sistem, tools=ARACLAR,
                        messages=mesajlar, output_config={"effort": EFOR}, **yedek,
                    ) as akis:
                        for olay in akis:
                            olay_ms = round((time.perf_counter() - akis_baslangic) * 1000)
                            if olcum["ilk_olay_ms"] is None:
                                olcum["ilk_olay_ms"] = olay_ms
                            if olay.type == "text" and olay.text:
                                if ilk_metin_ms is None:
                                    ilk_metin_ms = round((time.perf_counter() - baslangic) * 1000)
                                if olcum["ilk_metin_ms"] is None:
                                    olcum["ilk_metin_ms"] = olay_ms
                                olcum["son_metin_ms"] = olay_ms
                                olcum["metin_parcasi"] += 1
                                uretti = True
                                metin.append(olay.text)
                                yield {"type": "token", "delta": olay.text}
                        yanit = akis.get_final_message()
                    break
                except ValueError:
                    # SDK'nin hic ayristiramadigi arac girdisi: tur yeniden istenir.
                    json_denemesi += 1
                    if json_denemesi > 2:
                        raise
            girdi_token += getattr(yanit.usage, "input_tokens", 0) or 0
            cikti_token += getattr(yanit.usage, "output_tokens", 0) or 0
            if yanit.stop_reason == "refusal":
                if not metin:
                    metin.append("Bu isteği yanıtlayamıyorum.")
                    yield {"type": "token", "delta": metin[-1]}
                break
            kullanimlar = [b for b in yanit.content if b.type == "tool_use"]
            if not kullanimlar:
                break
            if yanit.stop_reason == "max_tokens":
                hata_notu = "Cevap uzunluk sınırına takıldı."
                break
            for blok in kullanimlar:
                araclar.append(blok.name)
                girdi = blok.input if isinstance(blok.input, dict) else {}
                etiket = ASAMA[blok.name](girdi) if blok.name in ASAMA else blok.name
                yield {"type": "stage", "label": etiket}
            with ThreadPoolExecutor(max_workers=len(kullanimlar)) as havuz:
                sonuclar = list(havuz.map(lambda b: arac_calistir(b, memory), kullanimlar))
            mesajlar.append({"role": "assistant", "content": yanit.content})
            mesajlar.append({"role": "user", "content": sonuclar})
            yield {"type": "stage", "label": "Cevabı yazıyorum"}
            if metin and not metin[-1].endswith("\n"):
                metin.append("\n\n")
                yield {"type": "token", "delta": "\n\n"}
        else:
            hata_notu = "Araç turu sınırına ulaşıldı; cevap eksik olabilir."
    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError, ValueError) as hata:
        if not uretti and not araclar:
            raise AjanKullanilamaz(f"{type(hata).__name__}: {str(hata)[:160]}") from None
        hata_notu = "Bağlantı sorunu nedeniyle cevap yarım kalmış olabilir."
    if hata_notu:
        metin.append(("\n\n" if metin else "") + "⚠ " + hata_notu)
        yield {"type": "token", "delta": metin[-1]}
    cevap = "".join(metin).strip() or "Bu soru için cevap üretilemedi. Lütfen yeniden deneyin."
    sure_ms = round((time.perf_counter() - baslangic) * 1000)
    _kaydet({"ts": datetime.now(timezone.utc).isoformat(), "sure_ms": sure_ms, "model": MODEL,
             "efor": EFOR, "cagri": cagri, "araclar": araclar, "girdi_token": girdi_token,
             "cikti_token": cikti_token, "not": hata_notu,
             "ilk_metin_ms": ilk_metin_ms, "akis_olcumleri": akis_olcumleri})
    yield {"type": "done", "result": {
        "intent": "AJAN", "status": "ANSWERED", "kind": "ANSWER", "answer": cevap, "text": cevap,
        "model": MODEL, "model_calls": cagri, "araclar": araclar, "duration_ms": sure_ms,
        "external_actions": 0}}
