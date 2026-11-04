"""L'CARLİÉ fiyat listesinden kategori bazlı referans fiyatlar."""
import json
import statistics

KATEGORILER = ["yuz", "vucut", "bebek", "gunes", "sac", "intim", "dudak", "agiz_dis", "roll_on", "sprey"]


class PriceBook:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.items = self.data["urunler"]
        self.campaigns = self.data.get("kampanyalar", [])
        self.overall = statistics.median(i["psf"] for i in self.items)
        self.by_cat = {}
        self.by_cat_ty = {}
        for i in self.items:
            self.by_cat.setdefault(i["kategori"], []).append(i["psf"])
            if i.get("trendyol"):
                self.by_cat_ty.setdefault(i["kategori"], []).append(i["trendyol"])
        ty = [i["trendyol"] for i in self.items if i.get("trendyol")]
        self.overall_ty = statistics.median(ty) if ty else self.overall

    def reference(self, category, trendyol=False):
        """Kategori medyan fiyat; kategori yoksa genel medyan.

        Trendyol'da görülen rakip fiyatı bizim Trendyol fiyatımızla (PSF'nin ~%15 üstü) karşılaştırılır;
        PSF ile karşılaştırmak rakibi olduğundan pahalı gösteriyordu.
        """
        tablo, genel = (self.by_cat_ty, self.overall_ty) if trendyol else (self.by_cat, self.overall)
        vals = tablo.get(category or "")
        return (statistics.median(vals), category) if vals else (genel, "genel")

    def band(self, price, category, min_ratio, trendyol=False):
        ref, used = self.reference(category, trendyol)
        ratio = price / ref
        return {"ref": ref, "ref_kategori": used, "oran": round(ratio, 2), "bantta": ratio >= min_ratio}
