"""Kampanya bütçesi, takvimi ve hedeflemesi -- ölçülen rakamlardan.

NEDEN VAR
Ajansın deney matrisi kelimesi kelimesine şunu yazıyordu:
    {"audience": "held constant", "budget": "held constant"}
Bunlar string; hedef kitle tanımı ya da bütçe rakamı değil. Bütçe modeli,
takvim ve kanal hedeflemesi kodda hiç yoktu.

NASIL HESAPLANIR -- HER SAYI ÖLÇÜLMÜŞ
  tıklama maliyeti : advertising_performance'tan (harcama / tıklama)
  birim marj       : sales_items'tan (brüt marj / adet)
  başabaş tıklama  : birim marj / tıklama maliyeti
Yani "şu kadar tıklamada bir satış olmazsa bu kampanya para kaybettirir".

NE BİLİNMİYOR VE SÖYLENİYOR
Gerçek dönüşüm oranı ÖLÇÜLMÜYOR: reklam kayıtlarında ticari doğrulama yok
(ölçüldü: 25 kaydın 0'ında). Dolayısıyla kampanyanın kâr edip etmeyeceği
ÖNCEDEN BİLİNEMEZ. Plan bunu gizlemez; test bütçesini bu belirsizliğe göre
sınırlar ve kararı insana bırakır.

NEDEN TAHMİNİ DÖNÜŞÜM ORANI UYDURULMUYOR
"Sektör ortalaması %2" demek kolay olurdu ve plan daha dolu görünürdü. Ama
o rakam bu şirketin verisi değildir; onunla hesaplanan bütçe, ölçülmüş gibi
duran bir tahmindir. Bilinmeyeni bilinmiyor diye yazmak, uydurulmuş bir
kesinlikten iyidir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Bir A/B farkini gorebilmek icin gereken asgari tiklama. Basabas tiklamanin
# KATI olarak ifade edilir: tek bir satis tesaduf olabilir, karar veremezsin.
MIN_TEST_MULTIPLE = 2.0
# Ustunde durulan azami: daha fazlasi ogrenme degil, harcamadir.
MAX_TEST_MULTIPLE = 3.0


@dataclass(frozen=True)
class Plan:
    product: str
    cpc: float | None
    unit_margin: float | None
    breakeven_clicks: float | None
    test_clicks: tuple[int, int] | None
    test_budget: tuple[float, float] | None
    daily_budget: float | None
    days: tuple[int, int] | None
    targeting: dict[str, Any] = field(default_factory=dict)
    unknowns: tuple[str, ...] = ()
    basis: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "cpc": self.cpc, "unit_margin": self.unit_margin,
            "breakeven_clicks": self.breakeven_clicks,
            "test_clicks": list(self.test_clicks) if self.test_clicks else None,
            "test_budget": list(self.test_budget) if self.test_budget else None,
            "daily_budget": self.daily_budget,
            "days": list(self.days) if self.days else None,
            "targeting": self.targeting,
            "unknowns": list(self.unknowns),
            "basis": list(self.basis),
        }


def _num(row: dict, *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def measured_cpc(ad_rows: list[dict[str, Any]]) -> tuple[float | None, str]:
    """Ölçülen tıklama maliyeti. Veri yoksa None -- varsayılan uydurulmaz."""
    rows = [r for r in ad_rows if r.get("pencere") == 30]
    harcama = sum(_num(r, "harcama") for r in rows)
    tiklama = sum(_num(r, "tiklama") for r in rows)
    if not (harcama and tiklama):
        return None, "30 günlük reklam verisi yok; tıklama maliyeti bilinmiyor."
    return round(harcama / tiklama, 2), (
        f"{len(rows)} reklam kaydı: {harcama:,.0f} TL / {tiklama:,.0f} tıklama")


def unit_margin(item_rows: list[dict[str, Any]], product_keys: tuple[str, ...]
                ) -> tuple[float | None, str]:
    """Bu ürünün ölçülen birim brüt marjı. Satışı yoksa None."""
    def uyar(row):
        ad = str(row.get("urun_adi") or "").casefold()
        return any(k and k in ad for k in product_keys)

    rows = [r for r in item_rows if uyar(r)]
    adet = sum(_num(r, "adet") for r in rows)
    marj = sum(_num(r, "brut_marj") for r in rows)
    bilinen = [r for r in rows if r.get("maliyeti_biliniyor")]
    if not (adet and marj):
        return None, "Bu ürünün ölçülmüş satışı yok; birim marj bilinmiyor."
    temel = f"{len(rows)} satış kalemi, {adet:,.0f} adet, {marj:,.0f} TL brüt marj"
    if len(bilinen) < len(rows):
        temel += f" ({len(rows) - len(bilinen)} kalemde maliyet bilinmiyor, marj şişik olabilir)"
    return round(marj / adet, 2), temel


def targeting_from_history(ad_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Geçmişte GERÇEKTEN kullanılmış kampanya ve kitle adları.

    "held constant" bir metindi. Sabit tutulacak sey ADIYLA yazilmazsa
    kampanya kurulamaz ve sonuc karsilastirilamaz.
    """
    rows = [r for r in ad_rows if r.get("pencere") == 30]
    kampanyalar, adsetler, reklamlar = {}, {}, {}
    for row in rows:
        for alan, kutu in (("kampanya_adi", kampanyalar), ("adset_adi", adsetler),
                           ("ad_adi", reklamlar)):
            ad = str(row.get(alan) or "").strip()
            if ad:
                kutu[ad] = kutu.get(ad, 0) + _num(row, "harcama")
    def sirala(kutu):
        return [{"name": ad, "spend": round(h, 2)}
                for ad, h in sorted(kutu.items(), key=lambda kv: -kv[1])[:6]]
    return {"campaigns": sirala(kampanyalar), "adsets": sirala(adsetler),
            "ads": sirala(reklamlar),
            "note": ("Bunlar GEÇMİŞTE kullanılmış adlardır; yeni testte "
                     "sabit tutulacak kitle bunlardan seçilmeli ki sonuç "
                     "öncekiyle karşılaştırılabilsin.")}


def build(product: str, ad_rows: list[dict[str, Any]],
          item_rows: list[dict[str, Any]],
          product_keys: tuple[str, ...] = (),
          daily_budget: float | None = None) -> Plan:
    """Ölçülen veriden kampanya planı. Bilinmeyen bilinmiyor diye yazılır."""
    keys = product_keys or (product.split("(")[0].strip().casefold(),)
    cpc, cpc_temel = measured_cpc(ad_rows)
    marj, marj_temel = unit_margin(item_rows, keys)

    bilinmeyen: list[str] = [
        # Bu, planin en onemli bilinmeyeni: onsuz kar/zarar ONCEDEN bilinemez.
        "gerçek dönüşüm oranı (reklam kayıtlarında ticari doğrulama yok)",
    ]
    if cpc is None:
        bilinmeyen.append("tıklama maliyeti")
    if marj is None:
        bilinmeyen.append("birim brüt marj")

    basabas = round(marj / cpc, 1) if (cpc and marj) else None
    test_tiklama = test_butce = gunler = None
    if basabas:
        alt = int(basabas * MIN_TEST_MULTIPLE)
        ust = int(basabas * MAX_TEST_MULTIPLE)
        test_tiklama = (alt, ust)
        test_butce = (round(alt * cpc, 2), round(ust * cpc, 2))
        if daily_budget and daily_budget > 0:
            gunluk_tiklama = daily_budget / cpc
            gunler = (max(1, int(alt / gunluk_tiklama)),
                      max(1, int(ust / gunluk_tiklama)) + 1)

    return Plan(
        product=product, cpc=cpc, unit_margin=marj, breakeven_clicks=basabas,
        test_clicks=test_tiklama, test_budget=test_butce,
        daily_budget=daily_budget, days=gunler,
        targeting=targeting_from_history(ad_rows),
        unknowns=tuple(bilinmeyen),
        basis=tuple(t for t in (cpc_temel, marj_temel) if t),
    )


def summarize(plan: Plan) -> str:
    """Planı tek paragrafta, her sayının nereden geldiğiyle birlikte."""
    if plan.cpc is None or plan.unit_margin is None:
        return ("Bütçe hesaplanamadı: "
                + "; ".join(plan.unknowns) + ". Ölçüm olmadan bütçe önermek, "
                "rakam uydurmak olurdu.")
    parcalar = [
        f"Ölçülen tıklama maliyeti {plan.cpc:,.2f} TL, {plan.product} birim "
        f"brüt marjı {plan.unit_margin:,.0f} TL.",
        f"Başabaş için {plan.breakeven_clicks:,.0f} tıklamada 1 satış gerekir.",
    ]
    if plan.test_budget:
        parcalar.append(
            f"Karar verebilmek için {plan.test_clicks[0]:,}-{plan.test_clicks[1]:,} "
            f"tıklama, yani {plan.test_budget[0]:,.0f}-{plan.test_budget[1]:,.0f} TL "
            f"test bütçesi gerekir.")
    if plan.days:
        parcalar.append(
            f"Günlük {plan.daily_budget:,.0f} TL ile bu {plan.days[0]}-{plan.days[1]} gün sürer.")
    parcalar.append(
        "Gerçek dönüşüm oranı ölçülmüyor, bu yüzden kâr edip etmeyeceği "
        "önceden bilinemez; test bütçesi bu belirsizlik için sınırlıdır.")
    return " ".join(parcalar)
