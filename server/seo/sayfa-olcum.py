"""Sayfalarin ARAMA MOTORUNA gorunen halini olcer.

🔴 Neden sunucudan olculuyor: Wix icerigi buyuk olcude tarayicida kuruyor.
Buradan gorulen sey, JS calistirmayan bir botun gordugudur. Bu "sayfa bos"
DEMEK DEGILDIR -- "JS'siz bakan gormuyor" demektir. Ikisi ayri sey.
"""
import json, re, subprocess, sys, urllib.parse, urllib.request
from html.parser import HTMLParser

BAS = {"User-Agent": "Mozilla/5.0 (compatible; LcarlieSEOAudit/1.0)"}

def cek(url):
    # 🔴 ADRESI KODLA. Turkce karakterli yol (ornek: .../minisooth-bebek-
    # pisik-kremi) ham halde gonderilince urllib hata veriyor ve olcum
    # "HTTP 0" yaziyordu. Bu, SAYFANIN bozuk oldugu anlamina gelmez --
    # OLCEN tarafin kusurudur. Iki durum ayri; karistirilirsa saglam sayfa
    # bozuk diye raporlanir (bir kez oldu).
    p = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit(
        (p.scheme, p.netloc, urllib.parse.quote(p.path), p.query, p.fragment))
    try:
        r = urllib.request.Request(url, headers=BAS)
        with urllib.request.urlopen(r, timeout=25) as c:
            return c.status, c.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, ""

class Ayikla(HTMLParser):
    def __init__(self):
        super().__init__()
        self.baslik = ""; self.meta = ""; self.kanonik = ""
        self.h1 = []; self._t = None; self._h1 = ""
        self.metin = []; self._yoksay = 0
    def handle_starttag(self, t, a):
        d = dict(a)
        if t == "title": self._t = "title"
        elif t == "h1": self._t = "h1"
        elif t in ("script", "style", "noscript"): self._yoksay += 1
        elif t == "meta" and d.get("name", "").lower() == "description":
            self.meta = d.get("content", "")
        elif t == "link" and "canonical" in d.get("rel", ""):
            self.kanonik = d.get("href", "")
    def handle_endtag(self, t):
        if t == "h1": self.h1.append(self._h1.strip()); self._h1 = ""
        if t in ("title", "h1"): self._t = None
        if t in ("script", "style", "noscript"): self._yoksay = max(0, self._yoksay - 1)
    def handle_data(self, d):
        if self._t == "title": self.baslik += d
        elif self._t == "h1": self._h1 += d
        elif not self._yoksay: self.metin.append(d)

def olc(url):
    kod, govde = cek(url)
    p = Ayikla()
    try: p.feed(govde)
    except Exception: pass
    kelime = len(" ".join(p.metin).split())
    return {"url": url, "http": kod, "baslik": " ".join(p.baslik.split()),
            "baslik_uz": len(" ".join(p.baslik.split())),
            "meta_uz": len(p.meta), "h1_adet": len(p.h1),
            "h1": (p.h1[0][:60] if p.h1 else ""),
            "kelime": kelime, "kanonik": p.kanonik, "bayt": len(govde)}

def harita(ad):
    _, x = cek("https://www.lcarlie.shop/%s-sitemap.xml" % ad)
    return re.findall(r"<loc>([^<]+)</loc>", x)

hedefler = [("urun", u) for u in harita("store-products")]
sabit = [u for u in harita("pages")
         if u.rstrip("/").rsplit("/", 1)[-1] in (
             "vireon", "babyline", "geceserisi", "gunes-ritueli", "gunlukkullanim",
             "hassas-cilt", "hedefli-bakim", "hydravie", "nem-bariyer", "ozelyaglar",
             "spor-ve-aktif-yasam", "temizlemedenge", "seninicin", "shop", "tumurunler")]
hedefler += [("sabit", u) for u in sabit]

sonuc = []
for tur, u in hedefler:
    r = olc(u); r["tur"] = tur; sonuc.append(r)
    print(".", end="", flush=True)
print()
json.dump(sonuc, open("/tmp/sayfa-olcum.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("olculen sayfa:", len(sonuc))
