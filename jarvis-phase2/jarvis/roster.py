"""Ekip listesi: kim, ne işe bakar, bu veriye bakınca ne diyor.

NEDEN VAR
Panelde 28 satır vardı: 8 ajans rolü + 20 uzman. Hiçbirinin adı Türkçe
değildi, görevi yazmıyordu ve ne düşündüğü görünmüyordu. Sahip 20.09.2026'da
"kimin ne dediğini, nasıl düşündüğünü görmek istiyorum" dedi.

Uzmanlar aslında rakamlı, alana özgü ifadeler üretiyordu -- ama İngilizce
("Sales bounded context: 37 orders...") ve panele hiç taşınmıyordu.

NE YAPAR
Her ekip üyesi için: Türkçe ad, tek cümlelik görev, okuduğu veri, ve o
veriye bakınca söylediği ŞEY. Sıfır model çağrısı -- hepsi sayımdır.

NE UYDURMAZ
Verisi olmayan üye "veriden konuşamam" der ve sebebini söyler. Altı üyenin
hiç veri kaynağı yok (pazar/rakip istihbaratı, araştırma, kırmızı takım,
strateji, genel müdür); bunlar ya dış araştırma ya da başkalarının
bulgusunu girdi alır. Onlara sahte bir cümle yazdırmak, paneli dolu
göstermek için yalan söylemek olurdu.

ÖLÇÜM PENCERESİ TUZAĞI
Satış ifadesi yalnız `olcumde` satırlarını sayarsa 0 çıkar (ölçüm 1 Ekim'de
başlıyor) ve "satış yok" gibi okunur. Aynı hata konuşma cevaplarında da
vardı ve düzeltildi. Burada da gerçek toplam verilir, çekince ayrıca yazılır.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# --- durumlar
SPEAKS = "KONUŞTU"          # veriye bakti, bir sey soyledi
NO_DATA = "VERİ YOK"        # kaynagi okunamadi
NEEDS_RESEARCH = "ARAŞTIRMA GEREKİR"   # dis kaynak olmadan konusamaz
NEEDS_INPUT = "GİRDİ BEKLER"           # baskalarinin bulgusunu girdi alir


@dataclass(frozen=True)
class Member:
    key: str
    name: str
    job: str
    reads: tuple[str, ...] = ()
    kind: str = "specialist"
    mode: str = "data"      # data | research | synthesis


# 20 uzman + 8 ajans rolu. Ad ve gorev Turkce; "reads" gercekten okudugu
# Company Memory sorgulari.
ROSTER: tuple[Member, ...] = (
    # --- veriden konusanlar
    Member("ecommerce_sales", "Satış Analisti",
           "Siparişleri ve kalemleri okur: kaç adet satıldı, ne kadar ciro oldu.",
           ("sales_orders", "sales_items")),
    Member("product_portfolio", "Ürün ve Portföy Uzmanı",
           "Ürün kârlılığını, fiyatları ve huniyi okur: hangi ürün para kazandırıyor.",
           ("ecommerce_profitability", "ecommerce_price", "ecommerce_funnel")),
    Member("meta_performance", "Meta Reklam Analisti",
           "Reklam harcaması, gösterim ve tıklamayı okur: reklamın ölçülen maliyeti.",
           ("advertising_performance", "advertising_spend")),
    Member("creative_intelligence", "Kreatif İstihbarat",
           "Reklam kayıtlarından hangi kreatifin tuttuğunu okur.",
           ("advertising_performance",)),
    Member("social_media", "Sosyal Medya Uzmanı",
           "Kanal performansını reklam verisinden okur.",
           ("advertising_performance",)),
    Member("crm_customer", "Müşteri İlişkileri Uzmanı",
           "Cevapsız mesajları ve bekleme sürelerini okur.",
           ("crm_customers", "crm_unanswered", "open_work")),
    Member("field_b2b_sales", "Kurumsal Satış Uzmanı",
           "Aynı sipariş verisini kurumsal kanal açısından okur.",
           ("sales_orders", "sales_items")),
    Member("operations", "Operasyon Uzmanı",
           "Kargo, gönderi ve açık işleri okur.",
           ("operations_shipments", "open_work")),
    Member("regulatory_quality", "Mevzuat ve Kalite Uzmanı",
           "Karar özetinden mevzuat riskini okur.",
           ("decision_summary",)),
    Member("data_measurement", "Ölçüm ve Veri Uzmanı",
           "Ölçümün kendisi güvenilir mi, ona bakar.",
           ("advertising_performance", "advertising_spend")),
    Member("growth", "Büyüme Uzmanı",
           "Karar özetinden büyüme sinyalini okur.",
           ("decision_summary",)),
    Member("ai_prompt_engineering", "Yapay Zekâ Altyapısı",
           "Model ve yetenek durumunu okur.",
           ("capability_state",)),
    # 🔴 20.09.2026: bu iki uye YAPISAL OLARAK SESSIZDI. Ikisi de 'financial'
    # adli bir sorgu okuyordu ve o sorgu izin listesinde HIC YOKTU; ustelik
    # ai_reader'in mart.ekonomi_gunluk ve mart.nakit_gunluk uzerinde hicbir
    # yetkisi de yoktu. Kadroda gorunup veriden tek cumle kuramiyorlardi.
    # Sorgular eklendi, yetki verildi, ikisine ayri okuma yazildi -- cunku
    # isleri ayri: biri birim ekonomiye, digeri kaydin tutarliligina bakar.
    Member("finance", "Finans Uzmanı",
           "Günlük birim ekonomiyi okur: net ciro, katkı ve reklam sonrası kâr.",
           ("financial",)),
    Member("accounting_control", "Muhasebe Kontrol",
           "Kaydın tutarlılığına bakar: tahsil edilmemiş tutar, maliyet kalitesi, hesap kapsaması.",
           ("financial_cash",)),
    # --- kreatif ve marka (20.09.2026, sahip talebiyle buyutuldu)
    # 🔴 EKIP BUYUTMENIN SARTI VERI. Her yeni uye BASKA bir gorunume,
    #    baska bir soruyla bakar; ayni veriye ikinci bir ad koymak "farkli
    #    fikir" uretmez, ayni cumleyi iki kere soyletir.
    Member("creative_decision", "Kreatif Karar Uzmanı",
           "Reklam bazında kararı okur: hangisi izlenecek, hangisi yüksek dikkat "
           "aldığı halde satışı doğrulanmamış, hangisi yetersiz örneklem.",
           ("creative_decisions",)),
    Member("creative_hypothesis", "Kreatif Hipotez Uzmanı",
           "Açık hipotezleri ve her birinin nasıl yanlışlanacağını okur.",
           ("creative_hypotheses",)),
    Member("creative_copy", "Başlık ve CTA Analisti",
           "Kreatif metnini performansla birlikte okur: hangi CTA ve hangi biçim "
           "daha çok link tıklaması getiriyor.",
           ("kreatif_performans",)),
    Member("creative_fatigue", "Kreatif Yorgunluk Analisti",
           "Frekansı okur: aynı kişi reklamı kaç kez görüyor, hangi kreatif yoruldu.",
           ("kreatif_performans",)),
    Member("brand_voice", "Müşteri Dili Uzmanı",
           "Müşterinin kendi sorduğu konuları okur: neyi soruyor, neyi hiç sormuyor.",
           ("customer_voice",)),
    Member("brand_positioning", "Konumlandırma Uzmanı",
           "Soru dağılımını fiyat gerçeğiyle birlikte okur: marka neyle anılıyor.",
           ("customer_voice", "ecommerce_price")),
    # Organik icerik (20.09.2026). Ucu de AYNI tabloya bakar ama UC AYRI
    # soruyla: ne siklikta yayinliyoruz / ne kadar karsilik goruyor / hangi
    # bicimde uretiyoruz. Ayni cumleyi uc kez soyletmemek icin sorular ayrildi.
    Member("content_cadence", "İçerik Ritmi Analisti",
           "Yayın ritmini ve metin alışkanlığını okur: ayda kaç gönderi, "
           "ne uzunlukta metin, kaç etiket, reklam ibaresi var mı.",
           ("content_performance",)),
    Member("social_engagement", "Sosyal Etkileşim Analisti",
           "Gönderi başına beğeni ve yorumu okur: hangi biçim karşılık görüyor.",
           ("content_performance",)),
    Member("art_format", "Görsel Format Analisti",
           "Üretim biçimini okur: reels mi, sabit görsel mi, hangisi ağır basıyor.",
           ("content_performance",)),
    Member("market_findings", "Pazar Bulgu Uzmanı",
           "Kayda geçmiş pazar bulgularını kaynağı ve tarihiyle okur.",
           ("market_research",)),
    # --- dis arastirma gerektirenler
    Member("market_intelligence", "Pazar İstihbaratı",
           "Pazarın dışarıdaki halini araştırır; şirket verisinden konuşamaz.",
           (), mode="research"),
    Member("competitor_intelligence", "Rakip İstihbaratı",
           "Rakiplerin hamlelerini dışarıdan araştırır.", (), mode="research"),
    Member("research", "Araştırmacı",
           "İnternette kaynak arar, bulduğunu tarih ve türüyle getirir.",
           (), mode="research"),
    # --- baskalarinin bulgusunu girdi alanlar
    Member("red_team", "Kırmızı Takım",
           "Diğerlerinin bulgusuna itiraz eder; kendi verisi yoktur.",
           (), mode="synthesis"),
    Member("strategy", "Strateji",
           "Bulguları karar seçeneğine çevirir.", (), mode="synthesis"),
    Member("managing_director", "Genel Müdür (sentez)",
           "Hepsini tek özete indirir ve çelişkiyi işaretler.",
           (), mode="synthesis"),
    # --- ajans rolleri (uretim tarafi)
    Member("CREATIVE_DIRECTOR", "Kreatif Direktör",
           "Kampanyanın açısını kurar, konseptleri belirler.",
           kind="agency", mode="synthesis"),
    Member("COPYWRITER", "Metin Yazarı",
           "Başlık ve reklam gövde metnini yazar.", kind="agency", mode="synthesis"),
    Member("META_PERFORMANCE", "Meta Performans (ajans)",
           "Kampanyanın reklam tabanını hesaplar.", kind="agency", mode="synthesis"),
    Member("CREATIVE_INTELLIGENCE", "Kreatif İstihbarat (ajans)",
           "Test planını ve deney matrisini kurar.", kind="agency", mode="synthesis"),
    Member("COMPETITOR_CREATIVE", "Rakip Kreatif",
           "Rakip reklamlarına bakılması gerektiğini işaretler.",
           kind="agency", mode="research"),
    Member("SOCIAL_CONTENT", "Sosyal İçerik",
           "Haftalık gönderi planını kurar.", kind="agency", mode="synthesis"),
    Member("CRO_SPECIALIST", "Dönüşüm Uzmanı",
           "Açılış sayfası önerilerini çıkarır.", kind="agency", mode="synthesis"),
    Member("GROWTH_STRATEGIST", "Büyüme Stratejisti",
           "Problem ve fırsatları listeler.", kind="agency", mode="synthesis"),
)

BY_KEY = {m.key: m for m in ROSTER}


# ------------------------------------------------------------- görüş üretimi
def _num(row: dict, *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _top(rows, key, value_key, reverse=True):
    """Bir alana göre en yüksek/düşük satır. Boşsa None."""
    adaylar = [r for r in rows if r.get(key) and _num(r, value_key)]
    if not adaylar:
        return None
    return sorted(adaylar, key=lambda r: _num(r, value_key), reverse=reverse)[0]


def _group_sum(rows, key, value_key):
    out: dict[str, float] = {}
    for row in rows:
        ad = str(row.get(key) or "").strip()
        if ad:
            out[ad] = out.get(ad, 0.0) + _num(row, value_key)
    return out


def _ads30(rows):
    return [r for r in rows.get("advertising_performance", []) if r.get("pencere") == 30]


def _say_sales(rows: dict[str, list]) -> str:
    """Satış Analisti: hacim, ciro ve en çok satan ürün."""
    orders, items = rows.get("sales_orders", []), rows.get("sales_items", [])
    adet = sum(int(r.get("adet") or 0) for r in items)
    ciro = sum(_num(r, "satir_ciro_net") for r in items)
    olcumde = sum(1 for r in orders if r.get("olcumde"))
    metin = (f"{len(orders)} siparişte {adet} adet ürün, {ciro:,.0f} TL net ciro.")
    urun_ciro = _group_sum(items, "urun_adi", "satir_ciro_net")
    if urun_ciro:
        en_iyi = max(urun_ciro.items(), key=lambda kv: kv[1])
        pay = en_iyi[1] / ciro * 100 if ciro else 0
        metin += (f" En çok ciro {en_iyi[0].split('(')[0].strip()[:28]}: "
                  f"{en_iyi[1]:,.0f} TL (cironun %{pay:.0f}'i).")
    # Sifir gostermek yerine sebebini soyle.
    if orders and olcumde == 0:
        metin += " Hiçbiri ölçüm penceresinde değil; satışlar yine de gerçek."
    return metin


def _say_b2b(rows: dict[str, list]) -> str:
    """Kurumsal Satış: hangi kanal satıyor."""
    orders = rows.get("sales_orders", [])
    if not orders:
        return "Sipariş kaydı yok."
    kanal = _group_sum(orders, "kanal", "ciro_beyan_edilmis_net")
    if not kanal:
        sayim: dict[str, int] = {}
        for r in orders:
            ad = str(r.get("kanal") or "bilinmiyor")
            sayim[ad] = sayim.get(ad, 0) + 1
        dagilim = ", ".join(f"{k}: {v}" for k, v in
                            sorted(sayim.items(), key=lambda kv: -kv[1])[:4])
        return f"{len(orders)} siparişin kanal dağılımı — {dagilim}."
    sirali = sorted(kanal.items(), key=lambda kv: -kv[1])
    toplam = sum(kanal.values()) or 1
    return ("Kanal bazında ciro — " + ", ".join(
        f"{ad}: {tutar:,.0f} TL (%{tutar / toplam * 100:.0f})"
        for ad, tutar in sirali[:4]) + ".")


def _say_ads(rows: dict[str, list]) -> str:
    """Meta Reklam Analisti: maliyet verimliliği."""
    perf = _ads30(rows)
    if not perf:
        return "30 günlük pencerede reklam kaydı yok."
    harcama = sum(_num(r, "harcama") for r in perf)
    gosterim = sum(int(r.get("gosterim") or 0) for r in perf)
    tiklama = sum(int(r.get("tiklama") or 0) for r in perf)
    aktif = sum(1 for r in perf if str(r.get("etkin_durum") or "").upper().startswith("ACTIVE"))
    cpc = harcama / tiklama if tiklama else 0
    cpm = harcama / gosterim * 1000 if gosterim else 0
    return (f"30 günde {harcama:,.0f} TL harcandı. Tıklama başı {cpc:,.2f} TL, "
            f"bin gösterim başı {cpm:,.2f} TL. {aktif}/{len(perf)} kayıt aktif.")


def _say_creative(rows: dict[str, list]) -> str:
    """Kreatif İstihbarat: hangi reklam metni tutuyor."""
    perf = [r for r in _ads30(rows) if r.get("ad_adi")]
    if not perf:
        return "Reklam bazında kayıt yok; hangi kreatifin tuttuğu ölçülemiyor."
    sirali = sorted(perf, key=lambda r: _num(r, "ctr_yuzde"), reverse=True)
    iyi, kotu = sirali[0], sirali[-1]
    return (f"{len(perf)} reklam karşılaştırıldı. En yüksek TO "
            f"'{str(iyi.get('ad_adi'))[:30]}' ile %{_num(iyi, 'ctr_yuzde'):.2f}; "
            f"en düşük '{str(kotu.get('ad_adi'))[:30]}' ile "
            f"%{_num(kotu, 'ctr_yuzde'):.2f}.")


def _say_social(rows: dict[str, list]) -> str:
    """Sosyal Medya: hangi kampanya/kitle erişiyor."""
    perf = _ads30(rows)
    if not perf:
        return "Kampanya bazında kayıt yok."
    erisim = _group_sum(perf, "kampanya_adi", "erisim")
    if not erisim:
        return f"{len(perf)} kayıt var ama kampanya adı taşımıyor."
    sirali = sorted(erisim.items(), key=lambda kv: -kv[1])
    toplam = sum(erisim.values()) or 1
    return (f"{len(sirali)} kampanya, toplam {toplam:,.0f} erişim. En geniş: "
            + ", ".join(f"{ad[:26]} ({v / toplam * 100:.0f}%)"
                        for ad, v in sirali[:3]) + ".")


def _say_measurement(rows: dict[str, list]) -> str:
    """Ölçüm ve Veri: ölçümün kendisi güvenilir mi."""
    perf = _ads30(rows)
    if not perf:
        return "Ölçülecek reklam kaydı yok."
    teyitli = sum(1 for r in perf if r.get("commercial_confirmation") == "CONFIRMED")
    meta_iddia = sum(_num(r, "meta_gelir_iddiasi") for r in perf)
    metin = (f"{len(perf)} kaydın {teyitli}'inde ticari doğrulama var "
             f"(%{teyitli / len(perf) * 100:.0f}).")
    if meta_iddia:
        metin += (f" Meta {meta_iddia:,.0f} TL gelir iddia ediyor; doğrulama "
                  f"olmadan bu rakam ciro sayılamaz.")
    else:
        metin += " Meta tarafında gelir iddiası da yok."
    return metin


def _say_crm(rows: dict[str, list]) -> str:
    """Müşteri İlişkileri: cevapsız ve bekleme."""
    cevapsiz = rows.get("crm_unanswered", [])
    musteri = rows.get("crm_customers", [])
    if not cevapsiz:
        return f"{len(musteri)} müşteri kaydı var, cevapsız konuşma görünmüyor."
    en_uzun = max((_num(r, "bekleme_saat") for r in cevapsiz), default=0)
    gun = en_uzun / 24
    return (f"{len(cevapsiz)} cevapsız müşteri konuşması var; en uzunu "
            f"{gun:.0f} gündür bekliyor. Toplam müşteri kaydı {len(musteri)}.")


def _say_products(rows: dict[str, list]) -> str:
    """Ürün ve Portföy: marj ve maliyet kapsaması."""
    kar = rows.get("ecommerce_profitability", [])
    fiyat = rows.get("ecommerce_price", [])
    eksik = sum(1 for r in kar if _num(r, "kapsama_yuzde") < 100)
    metin = f"Katalogda {len(fiyat)} ürün; {len(kar)} üründe kârlılık hesaplanabiliyor."
    if kar:
        # Karlilik gorunumunde URUN ADI YOK: `kalem` kalem SAYISIDIR ve kimlik
        # UUID. Ad fiyat listesinden entity_id ile eslestirilir -- olculdu:
        # 20 kaydin 19'u esleser. Eslesmeyen icin ad UYDURULMAZ.
        adlar = {}
        for satir in rows.get("ecommerce_price", []):
            adlar[str(satir.get("entity_id"))] = str(satir.get("urun_adi") or "")
        en_iyi = max(kar, key=lambda r: _num(r, "brut_marj"), default=None)
        if en_iyi is not None and _num(en_iyi, "brut_marj"):
            ad = adlar.get(str(en_iyi.get("entity_id"))) or "(adı eşleşmedi)"
            metin += (f" En yüksek brüt marj {ad.split('(')[0].strip()[:28]}: "
                      f"{_num(en_iyi, 'brut_marj'):,.0f} TL.")
    if eksik:
        metin += (f" {eksik} üründe maliyet kapsaması eksik; o ürünlerin marjı "
                  f"olduğundan iyi görünüyor.")
    return metin


def _say_operations(rows: dict[str, list]) -> str:
    """Operasyon: taşıyıcı, transit, alarm, kapıda ödeme."""
    gonderi = rows.get("operations_shipments", [])
    acik = rows.get("open_work", [])
    if not gonderi:
        return f"Gönderi kaydı yok; {len(acik)} açık iş var."
    alarmli = sum(1 for r in gonderi if r.get("alarm"))
    kapida = sum(1 for r in gonderi if r.get("cod_var"))
    transitler = [_num(r, "transit_gun") for r in gonderi if _num(r, "transit_gun")]
    ort = sum(transitler) / len(transitler) if transitler else 0
    tasiyici = _group_sum(gonderi, "tasiyici", "kargo_ucreti")
    metin = f"{len(gonderi)} gönderi; ortalama transit {ort:.1f} gün."
    if alarmli:
        metin += f" {alarmli} gönderide alarm var."
    if kapida:
        metin += f" {kapida} gönderi kapıda ödeme."
    if tasiyici:
        ad, ucret = max(tasiyici.items(), key=lambda kv: kv[1])
        metin += f" En çok kargo ücreti {ad[:20]}: {ucret:,.0f} TL."
    if acik:
        metin += f" {len(acik)} açık iş."
    return metin


def _say_decisions(rows: dict[str, list]) -> str:
    kararlar = rows.get("decision_summary", [])
    if not kararlar:
        return "Karar özeti boş."
    return f"{len(kararlar)} karar kaydı okunabiliyor."


def _say_capability(rows: dict[str, list]) -> str:
    durum = rows.get("capability_state", [])
    return (f"{len(durum)} yetenek kaydı okunabiliyor."
            if durum else "Yetenek durumu okunamadı.")


# Hangi uye hangi cumleyi kurar. Ayni veriyi okuyan iki uye ayni cumleyi
# kurar -- bu bir kusur degil, gercegin kendisi: ikisi de ayni gorunume
# bakiyor. Panel bunu gizlemez.
def _say_creative_decision(rows: dict[str, list]) -> str:
    """Kreatif Karar: etikete gore sayim. CTR'yi satis SAYMAZ."""
    k = rows.get("creative_decisions", [])
    if not k:
        return "Kreatif karar görünümü boş."
    etiket: dict[str, int] = {}
    for r in k:
        etiket[str(r.get("etiket") or "?")] = etiket.get(str(r.get("etiket") or "?"), 0) + 1
    dogrulanan = sum(1 for r in k
                     if str(r.get("commercial_confirmation") or "") not in ("", "NOT_AVAILABLE"))
    sirali = sorted(etiket.items(), key=lambda kv: -kv[1])
    metin = (f"{len(k)} reklam kararı: "
             + "; ".join(f"{ad} {n}" for ad, n in sirali[:4]) + ".")
    # 🔴 Bu cumle kaldirilamaz: yuksek CTR'yi "kazanan reklam" diye okumak
    #    bu projede acikca yasak, cunku atif kurulamiyor.
    metin += (f" Ticari doğrulaması olan reklam: {dogrulanan}/{len(k)}. "
              f"Doğrulama yoksa CTR yalnız dikkat ölçer, satış değil.")
    return metin


def _say_creative_hypothesis(rows: dict[str, list]) -> str:
    """Kreatif Hipotez: acik hipotez ve nasil yanlislanacagi."""
    h = rows.get("creative_hypotheses", [])
    if not h:
        return "Açık kreatif hipotezi yok."
    yanlislanabilir = sum(1 for r in h if str(r.get("yanlislama") or "").strip())
    metin = f"{len(h)} açık kreatif hipotezi var; {yanlislanabilir}'inde yanlışlama koşulu yazılı."
    ilk = h[0]
    konu = str(ilk.get("hipotez") or "")[:90]
    if konu:
        metin += f" En üstteki: “{konu}”."
    if yanlislanabilir < len(h):
        metin += (f" {len(h) - yanlislanabilir} hipotezin yanlışlama koşulu yok — "
                  f"çürütülemeyen hipotez sınanamaz.")
    return metin


def _say_creative_copy(rows: dict[str, list]) -> str:
    """Baslik ve CTA: CTA ve bicim kirilimi. Farkli CTA'lar KIYASLANAMAZ."""
    k = [r for r in rows.get("kreatif_performans", []) if r.get("yeterli_ornek")]
    if not k:
        return "Değerlendirilebilir kreatif yok (hepsi örneklem altında)."
    def kirilim(alan: str) -> list[tuple[str, float, int]]:
        kova: dict[str, list[float]] = {}
        for r in k:
            ad = str(r.get(alan) or "(yok)")
            kova.setdefault(ad, []).append(_num(r, "link_ctr"))
        return sorted(((ad, sum(v) / len(v), len(v)) for ad, v in kova.items()),
                      key=lambda t: -t[1])
    cta = kirilim("cta")[:3]
    bicim = kirilim("bicim")[:2]
    metin = (f"{len(k)} ölçülebilir kreatif. CTA'ya göre link CTR — "
             + "; ".join(f"{ad} %{o:.1f} ({n})" for ad, o, n in cta) + ".")
    if bicim:
        metin += " Biçim — " + "; ".join(f"{ad} %{o:.1f}" for ad, o, _ in bicim) + "."
    metin += (" Dikkat: farklı CTA'lar farklı şey satın alır; profil görüntüleme "
              "tıklaması ucuzdur ama satış değildir, bu oranlar doğrudan kıyaslanamaz.")
    return metin


def _say_creative_fatigue(rows: dict[str, list]) -> str:
    """Kreatif Yorgunluk: frekans. Ayni kisi kac kez gordu."""
    k = rows.get("kreatif_performans", [])
    if not k:
        return "Frekans okunabilecek kreatif yok."
    yorgun = [r for r in k if _num(r, "en_yuksek_frekans") >= 2.5]
    en_yuksek = max((_num(r, "en_yuksek_frekans") for r in k), default=0.0)
    metin = f"{len(k)} kreatifin {len(yorgun)}'inde frekans 2,5'in üstünde."
    if en_yuksek:
        metin += f" En yüksek frekans {en_yuksek:.1f}."
    if yorgun:
        metin += (" Aynı kişi reklamı tekrar tekrar görüyor; yeni açı üretilmezse "
                  "harcama aynı kitleye biner.")
    else:
        metin += " Yorgunluk sinyali yok."
    return metin


def _say_brand_voice(rows: dict[str, list]) -> str:
    """Musteri Dili: musterinin KENDI sordugu konular. Marka ne ile aniliyor."""
    s = rows.get("customer_voice", [])
    if not s:
        return "Müşteri soru dağılımı okunamıyor."
    sirali = sorted(s, key=lambda r: -_num(r, "konusma_yuzde"))
    ust = sirali[:3]
    dip = [r for r in sirali if _num(r, "konusma_yuzde") <= 1]
    metin = ("Müşterinin sorduğu konular — "
             + "; ".join(f"{r.get('konu')} %{_num(r,'konusma_yuzde'):.0f}" for r in ust) + ".")
    if dip:
        metin += (" Neredeyse hiç sorulmayanlar: "
                  + ", ".join(str(r.get("konu")) for r in dip[:3]) + ".")
    metin += (" Sorulmayan konu, ilgi olmadığını değil, o konunun müşteriye hiç "
              "ulaşmadığını da gösterebilir.")
    return metin


def _say_brand_positioning(rows: dict[str, list]) -> str:
    """Konumlandirma: soru dagilimi ile fiyat gercegini YAN YANA koyar."""
    s = rows.get("customer_voice", [])
    f = rows.get("ecommerce_price", [])
    if not s:
        return "Konumlandırma için soru dağılımı okunamıyor."
    toplam = sum(_num(r, "konusma_yuzde") for r in s) or 1.0
    fiyat = next((r for r in s if str(r.get("konu")) == "FIYAT"), None)
    icerik = next((r for r in s if str(r.get("konu")) == "ICERIK"), None)
    fayda = next((r for r in s if str(r.get("konu")) == "ETKI_FAYDA"), None)
    parcalar = []
    if fiyat is not None:
        parcalar.append(f"fiyat %{_num(fiyat,'konusma_yuzde'):.0f}")
    if icerik is not None:
        parcalar.append(f"içerik %{_num(icerik,'konusma_yuzde'):.0f}")
    if fayda is not None:
        parcalar.append(f"fayda %{_num(fayda,'konusma_yuzde'):.0f}")
    metin = f"Katalogda {len(f)} ürün var. Konuşmaların " + ", ".join(parcalar) + " ile açılıyor."
    if fiyat is not None and fayda is not None:
        fo, fa = _num(fiyat, "konusma_yuzde"), _num(fayda, "konusma_yuzde")
        if fa and fo / fa >= 3:
            metin += (f" Fiyat sorusu fayda sorusunun {fo/fa:.0f} katı: marka şu an "
                      f"ürünün ne yaptığıyla değil, ne kadar olduğuyla anılıyor.")
    return metin


def _ay_kova(icerik: list) -> dict[str, int]:
    kova: dict[str, int] = {}
    for r in icerik:
        gun = str(r.get("observed_at") or "")[:7]
        if gun:
            kova[gun] = kova.get(gun, 0) + 1
    return kova


def _say_content_cadence(rows: dict[str, list]) -> str:
    """Icerik Ritmi: ne siklikta yayinliyoruz, metin aliskanligi ne."""
    i = rows.get("content_performance", [])
    if not i:
        return "Organik içerik verisi okunamıyor."
    aylar = _ay_kova(i)
    ort_ay = sum(aylar.values()) / len(aylar) if aylar else 0
    uzunluk = [_num(r, "icerik_uzunluk") for r in i if _num(r, "icerik_uzunluk")]
    etiket = [_num(r, "etiket_sayisi") for r in i]
    ibaresiz = sum(1 for r in i if not r.get("reklam_ibaresi"))
    metin = (f"{len(i)} gönderi, {len(aylar)} ay: ayda ortalama {ort_ay:.1f} gönderi.")
    if uzunluk:
        metin += f" Metin ortalama {sum(uzunluk)/len(uzunluk):.0f} karakter"
    if etiket:
        metin += f", ortalama {sum(etiket)/len(etiket):.1f} etiket."
    if aylar:
        en_dusuk = min(aylar.items(), key=lambda kv: kv[1])
        metin += f" En az üretilen ay {en_dusuk[0]} ({en_dusuk[1]} gönderi)."
    # 🔴 Mevzuat izi sessiz gecilmez: reklam iceren gonderide ibare zorunlu.
    if ibaresiz:
        metin += (f" {ibaresiz} gönderide reklam/tanıtım ibaresi geçmiyor; "
                  f"reklam niteliği taşıyorlarsa ibare zorunludur.")
    return metin


def _say_social_engagement(rows: dict[str, list]) -> str:
    """Sosyal Etkilesim: begeni ve yorum. ORAN DEGIL SAYI -- erisim bilinmiyor."""
    i = rows.get("content_performance", [])
    if not i:
        return "Etkileşim okunabilecek gönderi yok."
    kova: dict[str, list[float]] = {}
    for r in i:
        kova.setdefault(str(r.get("bicim") or "?"), []).append(_num(r, "etkilesim"))
    sirali = sorted(((ad, sum(v) / len(v), len(v)) for ad, v in kova.items()),
                    key=lambda t: -t[1])
    begeni = sum(_num(r, "begeni") for r in i)
    yorum = sum(_num(r, "yorum") for r in i)
    metin = ("Biçim başına ortalama etkileşim — "
             + "; ".join(f"{ad} {o:.1f} ({n} gönderi)" for ad, o, n in sirali) + ".")
    metin += f" Toplam {begeni:,.0f} beğeni, {yorum:,.0f} yorum."
    if begeni and yorum / max(begeni, 1) < 0.02:
        metin += (" Yorum/beğeni oranı %2'nin altında: içerik beğeni topluyor "
                  "ama konuşma başlatmıyor.")
    # 🔴 Bu uyari kaldirilamaz.
    metin += (" Erişim verisi alınamıyor (izin yok), bu yüzden bunlar SAYIDIR; "
              "etkileşim oranı hesaplanamaz.")
    return metin


def _say_art_format(rows: dict[str, list]) -> str:
    """Gorsel Format: ne uretiyoruz. Uretim karmasi, karsiligi degil."""
    i = rows.get("content_performance", [])
    if not i:
        return "Format okunabilecek gönderi yok."
    bicim: dict[str, int] = {}
    tur: dict[str, int] = {}
    for r in i:
        bicim[str(r.get("bicim") or "?")] = bicim.get(str(r.get("bicim") or "?"), 0) + 1
        tur[str(r.get("tur") or "?")] = tur.get(str(r.get("tur") or "?"), 0) + 1
    toplam = len(i)
    sirali = sorted(bicim.items(), key=lambda kv: -kv[1])
    metin = ("Üretim karması — "
             + "; ".join(f"{ad} {n} (%{100*n/toplam:.0f})" for ad, n in sirali) + ".")
    video = sum(n for ad, n in tur.items() if ad == "VIDEO")
    if video:
        metin += f" Videolu içerik {video}/{toplam} (%{100*video/toplam:.0f})."
    yz = sum(1 for r in i if r.get("yz_beyani"))
    if yz:
        metin += (f" {yz} gönderide yapay zekâ beyanı var (%{100*yz/toplam:.0f}); "
                  f"görsel üretimin ağırlığı burada okunuyor.")
    return metin


def _say_market_findings(rows: dict[str, list]) -> str:
    """Pazar Bulgu: kayitli bulgular, kaynagiyla. Kaynaksiz bulgu sayilmaz."""
    p = rows.get("market_research", [])
    if not p:
        return "Kayda geçmiş pazar bulgusu yok."
    kaynakli = sum(1 for r in p if str(r.get("kaynak") or "").strip())
    metin = f"{len(p)} pazar bulgusu kayıtlı; {kaynakli}'i kaynağıyla birlikte."
    ilk = p[0]
    bulgu = str(ilk.get("bulgu") or "")[:90]
    if bulgu:
        metin += f" En yeni: “{bulgu}”."
    if kaynakli < len(p):
        metin += f" {len(p)-kaynakli} bulgunun kaynağı yok; doğrulanana kadar iddia sayılmaz."
    return metin


def _say_finance(rows: dict[str, list]) -> str:
    """Finans: gunluk birim ekonomi. Sifir model cagrisi, hepsi sayimdir."""
    gunler = rows.get("financial", [])
    if not gunler:
        return "Ekonomi görünümü boş; birim ekonomi hesaplanamıyor."
    son = gunler[0]
    harcama = sum(_num(g, "reklam_harcamasi") for g in gunler)
    ciro = sum(_num(g, "net_ciro") for g in gunler)
    katki = sum(_num(g, "reklam_sonrasi_katki") for g in gunler)
    # 🔴 "Siparis yok" ile "olculemedi" AYRI SEYLER. ekonomi_durumu alani
    #    bunu zaten ayiriyor; kendi yorumumu ustune koymuyorum.
    harcamali_siparissiz = sum(1 for g in gunler
                               if str(g.get("ekonomi_durumu") or "") == "HARCAMA_VAR_SIPARIS_YOK")
    metin = (f"Son {len(gunler)} günde net ciro {ciro:,.0f} TL, reklam harcaması "
             f"{harcama:,.0f} TL, reklam sonrası katkı {katki:,.0f} TL.")
    if harcamali_siparissiz:
        metin += (f" {harcamali_siparissiz} günde harcama var ama sipariş yok "
                  f"(ekonomi_durumu=HARCAMA_VAR_SIPARIS_YOK).")
    tamlik = _num(son, "ekonomi_tamlik_yuzde")
    if tamlik and tamlik < 100:
        metin += (f" En son günün ekonomi tamlığı %{tamlik:,.0f}; eksik bileşen "
                  f"varken katkı olduğundan iyi görünür.")
    return metin


def _say_accounting(rows: dict[str, list]) -> str:
    """Muhasebe Kontrol: kaydin tutarliligi -- rakamin kendisi degil, guvenilirligi."""
    gunler = rows.get("financial_cash", [])
    if not gunler:
        return "Nakit görünümü boş; kayıt tutarlılığı denetlenemiyor."
    tahsil_edilmemis = sum(_num(g, "tahsil_edilmemis") for g in gunler)
    brut = sum(_num(g, "brut_ciro") for g in gunler)
    olculmus = [_num(g, "cogs_olculmus_yuzde") for g in gunler
                if _num(g, "cogs_olculmus_yuzde")]
    metin = (f"Son {len(gunler)} günde brüt ciro {brut:,.0f} TL; "
             f"tahsil edilmemiş {tahsil_edilmemis:,.0f} TL.")
    if olculmus:
        metin += f" Maliyetin ölçülmüş kısmı ortalama %{sum(olculmus)/len(olculmus):,.0f}."
    else:
        metin += " Maliyetin ölçülmüş kısmı yok; marj tahminî maliyetle hesaplanıyor."
    # Meta hesap kapsamasi: eksikse reklam harcamasi OLDUGUNDAN DUSUK gorunur,
    # yani kar OLDUGUNDAN YUKSEK. Bu sessiz gecilemez.
    kapsama = [str(g.get("meta_hesap_kapsamasi") or "") for g in gunler]
    eksik_kapsama = [k for k in kapsama if k and k != "TAM" and "1/1" not in k]
    if eksik_kapsama:
        metin += (f" Reklam hesabı kapsaması eksik ({eksik_kapsama[0]}): "
                  f"harcama olduğundan düşük, dolayısıyla kâr olduğundan yüksek görünür.")
    return metin


SPEAKERS: dict[str, Callable[[dict[str, list]], str]] = {
    "finance": _say_finance,
    "accounting_control": _say_accounting,
    # kreatif + marka (20.09.2026)
    "creative_decision": _say_creative_decision,
    "creative_hypothesis": _say_creative_hypothesis,
    "creative_copy": _say_creative_copy,
    "creative_fatigue": _say_creative_fatigue,
    "brand_voice": _say_brand_voice,
    "brand_positioning": _say_brand_positioning,
    "market_findings": _say_market_findings,
    # organik icerik (20.09.2026)
    "content_cadence": _say_content_cadence,
    "social_engagement": _say_social_engagement,
    "art_format": _say_art_format,
    "ecommerce_sales": _say_sales,
    "field_b2b_sales": _say_b2b,
    "meta_performance": _say_ads,
    "creative_intelligence": _say_creative,
    "social_media": _say_social,
    "data_measurement": _say_measurement,
    "crm_customer": _say_crm,
    "product_portfolio": _say_products,
    "operations": _say_operations,
    "regulatory_quality": _say_decisions,
    "growth": _say_decisions,
    "ai_prompt_engineering": _say_capability,
}


def opinions(memory: Any, only: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Her ekip üyesinin bu veriye bakınca söylediği. Sıfır model çağrısı.

    Veri okunamazsa uye "VERI YOK" der ve hangi sorgunun okunamadigini
    soyler. Dis arastirma gerektirenler ve sentez rolleri kendi durumlarini
    bildirir; onlara sahte bir cumle yazdirmak paneli dolu gostermek icin
    yalan olurdu.
    """
    cache: dict[str, list] = {}
    out: list[dict[str, Any]] = []

    for member in ROSTER:
        if only and member.key not in only:
            continue
        kayit: dict[str, Any] = {
            "key": member.key, "name": member.name, "job": member.job,
            "kind": member.kind, "reads": list(member.reads),
            "model_calls": 0,
        }
        if member.mode == "research":
            kayit.update(status=NEEDS_RESEARCH,
                         statement="Şirket verisinden konuşamam; dış kaynak "
                                   "araştırması gerekir.")
            out.append(kayit)
            continue
        if member.mode == "synthesis":
            kayit.update(status=NEEDS_INPUT,
                         statement="Kendi verim yok; diğerlerinin bulgusunu "
                                   "girdi alırım.")
            out.append(kayit)
            continue

        rows: dict[str, list] = {}
        eksik: list[str] = []
        for query in member.reads:
            if query in cache:
                rows[query] = cache[query]
                continue
            try:
                kayitlar = list(memory._fetch(query).records)
            except Exception:  # noqa: BLE001 - okunamayan sorgu bir durumdur
                eksik.append(query)
                continue
            cache[query] = kayitlar
            rows[query] = kayitlar

        konusmaci = SPEAKERS.get(member.key)
        if eksik and not rows:
            kayit.update(status=NO_DATA, missing=eksik,
                         statement="Okuması gereken veri açık değil: "
                                   + ", ".join(eksik))
        elif konusmaci is None:
            kayit.update(status=NO_DATA,
                         statement="Bu üye için henüz bir okuma tanımlı değil.")
        else:
            kayit.update(status=SPEAKS, statement=konusmaci(rows),
                         rows={q: len(r) for q, r in rows.items()})
            if eksik:
                kayit["missing"] = eksik
        out.append(kayit)
    return out
