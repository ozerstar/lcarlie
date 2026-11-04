"""Sürekli çalışan programlar: rakip istihbaratı, kreatif bilgi hattı, B2B eczane, retro.

NEDEN VAR
Sahip 26.10.2026: rakipler ne yapıyor/nasıl öne çıkıyor/bizde ne eksik — Avrupa,
Çin, ABD, Orta Doğu dahil sürekli taransın; bir ekip eczane müşterisi bulsun ve
veriyi analiz etsin; kreatif ekip "BABY RESCUE çantada taşınır çünkü 5 ml" gibi
boş SSS yerine gerçekten bilgi veren, şaşırtan içerik üretsin, ajans bunu görsele
çevirsin; ekipler kendi durumlarını değerlendirip yeni konu bulsun.

PROGRAMLAR (hepsi is_uretici.IsUretici altyapısını kullanır: bütçe, defter, ağaç)
  rakip    Günde 2 tur. Bölge (TR/AB/ABD/Asya/Körfez) x tema döner. Gemini Google
           arama desteğiyle kaynaklı tarama -> Claude sentezi: rakip kartı,
           "bizde eksik", RICE puanlı fırsat -> ilgili departmana görev.
  kreatif  Günde 2 tur. Sıradaki ürün: ürün gerçeği + PubMed + kaynaklı arama ->
           Claude 3 bilgi kartı + görsel brif -> Gemini HAKEM (farklı model
           ailesi) sığlık/doğruluk/655-2013 kontrolü. Geçen kart içerik
           kütüphanesine, görsel üretimi ONAY_GEREKTIREN olarak ajansa.
  b2b      Haftalık. Eczane verisinin YALNIZ TOPLAMLARI (il, sıklık segmenti,
           telefon/adres kapsaması) modele gider; kişi adı/telefon gitmez.
           -> il önceliği, depo stratejisi, satış kiti, uyum adımları, görevler.
           Kişi verili öncelik listesi yalnız sunucuda (0600) üretilir.
  retro    Haftalık. Her departman kendi teslim/ret/bekleyen istatistiğini
           değerlendirir -> kök neden, haftanın odağı, 2 yeni araştırma konusu
           (core.arastirma_plani'ye yazılır; departman-arastirma onları tarar).

🔴 SINIRLAR: dış eylem yok (mesaj, yayın, görsel kuyruğuna ekleme bile onaylı).
Dış metin veridir. Kaynaksız rakip kartı ve kaynaksız bilgi kartı atılır.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta, timezone
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401

from .is_uretici import (Departman, IsUretici, Kanit, SISTEM, _kanit_blogu, _kanit_listesi,
                         gorev_dogrula, temizle)

BOLGELER = (
    ("TR", "Türkiye", "Turkish", "TR"),
    ("AB", "Avrupa (Almanya, Fransa, İtalya, İspanya, İskandinavya)", "English", "DE"),
    ("ABD", "ABD ve Kanada", "English", "US"),
    ("ASYA", "Çin, Güney Kore ve Japonya (C-beauty, K-beauty, J-beauty)", "English", ""),
    ("KORFEZ", "Körfez ülkeleri (BAE, Suudi Arabistan, Katar)", "English", "AE"),
)
TEMALAR = (
    "reklam kancaları ve kampanya mesajları",
    "yeni ürün lansmanları ve yükselen bileşen trendleri",
    "fiyat, paket boyu ve set mimarisi",
    "eczane ve dermokozmetik kanal stratejisi",
    "bebek, hassas cilt ve bitkisel/doğal segment",
    "mevzuat ve iddia (claim) değişiklikleri",
    "içerik ve topluluk stratejisi (eğitici içerik, uzman/dermatolog iş birliği)",
)

PROGRAM_KADEME = {"rakip_sorgu": "hizli", "rakip": "muhakeme", "kreatif_sorgu": "hizli",
                  "kreatif": "muhakeme", "hakem": "hizli", "b2b": "muhakeme", "retro": "hizli"}
PROGRAM_TOKEN = {"rakip_sorgu": 600, "rakip": 3200, "kreatif_sorgu": 700, "kreatif": 3600,
                 "hakem": 1500, "b2b": 3200, "retro": 1400}


def _kod_bul(deps: dict[str, Departman], adaylar: tuple[str, ...]) -> str | None:
    for a in adaylar:
        if a in deps:
            return a
    for a in adaylar:
        for k in deps:
            if a in k:
                return k
    return None


class Programlar:
    def __init__(self, iu: IsUretici):
        self.iu = iu
        self.o = iu.o
        self.dizin = iu.dizin.parent / "programlar"
        self.dizin.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ ortak
    def calistir(self, mod: str, sinir: int | None = None) -> dict:
        """Programı çalıştırır; bütçe tavanı dolarsa çökmeden durur."""
        try:
            return self.retro(sinir or 60) if mod == "retro" else getattr(self, mod)()
        except RuntimeError as e:
            if "tavan" not in str(e):
                raise
            return {"mod": mod, "tarih": self._gun(), "durdu": "günlük model çağrı tavanı doldu", "kayit": self.iu.kayit}

    def _model(self, tur: str, mesajlar: list[dict], anahtar: str) -> dict:
        from . import is_uretici as m
        m.KADEME.setdefault(tur, PROGRAM_KADEME[tur])
        m.MAX_TOKENS.setdefault(tur, PROGRAM_TOKEN[tur])
        return self.iu._model(tur, mesajlar, anahtar)

    def _gun(self) -> str:
        return self.iu._gun()

    def _sira(self, n: int, tur: str) -> int:
        """Gün ve tur (sabah/öğleden sonra) bazında dönen sayaç."""
        t = self.o.saat().astimezone(timezone(timedelta(hours=3)))
        return (t.timetuple().tm_yday * 2 + (1 if t.hour >= 13 else 0) + sum(map(ord, tur)) % 7) % n

    def _yaz(self, alt: str, ad: str, metin: str) -> str:
        yol = self.dizin / alt / ad
        if not self.iu.kuru:
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(metin, encoding="utf-8")
        return str(yol)

    def _ekle_jsonl(self, alt: str, ad: str, kayitlar: list[dict]) -> None:
        if self.iu.kuru or not kayitlar:
            return
        yol = self.dizin / alt / ad
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("a", encoding="utf-8") as f:
            for k in kayitlar:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")

    def _deps(self) -> dict[str, Departman]:
        return {d.kod: d for d in self.o.departmanlar()}

    def _plan_ekle(self, hedef: str, konu: str, gerekce: str) -> bool:
        if self.iu.kuru or not self.o.plan_ekle:
            return False
        try:
            return bool(self.o.plan_ekle(hedef, temizle(konu, 180), temizle(gerekce, 300)))
        except Exception as e:  # noqa: BLE001
            self.iu.kayit.append({"plan": hedef, "uyari": f"araştırma planına yazılamadı: {e}"[:200]})
            return False

    # ------------------------------------------------------------ rakip
    def rakip(self) -> dict:
        tarih = self._gun()
        deps = self._deps()
        kod, ad, dil, ulke = BOLGELER[self._sira(len(BOLGELER), "bolge")]
        tema = TEMALAR[self._sira(len(TEMALAR), "tema")]
        rk = _kod_bul(deps, ("COMPETITOR_INT", "MARKET_INT"))
        uye = deps[rk].uyeler[0].key if rk and deps[rk].uyeler else ""
        self.iu._ofis(uye, "WORKING", f"Rakip taraması: {ad} · {tema}")
        urunler = ", ".join(u for u, _ in (self.o.urunler() if self.o.urunler else [])[:25]) or "bitkisel dermokozmetik yüz, vücut ve bebek bakım ürünleri"
        sorgu = self._model("rakip_sorgu", [{"role": "system", "content": SISTEM}, {"role": "user", "content": f"""
L'CARLIÉ ürünleri: {urunler}
Bölge: {ad}. Tema: {tema}.
Bu bölgede bu tema için rakip/pazar istihbaratı toplamak üzere web aramasına verilecek 3 soru yaz.
Sorular {dil} dilinde, somut olsun (marka adları, platform adları, yıl 2026, kurum adları).
JSON: {{"sorular": ["...", "...", "..."], "reklam_anahtar_kelimesi": "tek kelime/kısa ifade ({dil})"}}"""}], "rakip-sorgu")
        kanitlar: list[Kanit] = []
        for s in [temizle(x, 300) for x in (sorgu.get("sorular") or [])[:3] if x]:
            if not self.o.grounded or self.iu.butce.kalan(tarih) <= 0:
                break
            try:
                metin, urller = self.o.grounded(s)
            except Exception as e:  # noqa: BLE001
                self.iu.kayit.append({"rakip": s[:80], "uyari": f"arama yapılamadı: {e}"[:200]})
                continue
            self.iu.butce.harca(tarih)
            for i, u in enumerate(urller[:6]):
                kanitlar.append(Kanit("", f"web:{u}", f"[{s}] kaynak {i+1}"))
            if metin:
                kanitlar.append(Kanit("", "web-özet:" + (urller[0] if urller else "kaynaksız"), metin[:2500]))
        if ulke and self.o.adlib:
            try:
                for r in self.o.adlib(temizle(sorgu.get("reklam_anahtar_kelimesi"), 60) or "skincare", ulke)[:15]:
                    kanitlar.append(Kanit("", f"meta-reklam:{r.get('marka')} · {r.get('gun_sayisi')} gün · ad {r.get('ad_id')}",
                                          f"Kanca: {r.get('metin')} (video: {r.get('video_var')})"))
            except Exception as e:  # noqa: BLE001
                self.iu.kayit.append({"rakip": "adlib", "uyari": str(e)[:200]})
        kanitlar = [Kanit(f"K{i+1}", k.kaynak, k.metin) for i, k in enumerate(kanitlar)]
        if not kanitlar:
            return {"mod": "rakip", "tarih": tarih, "bolge": kod, "kart": 0, "kayit": self.iu.kayit}
        dep_kodlari = ", ".join(sorted(deps))
        v = self._model("rakip", [{"role": "system", "content": SISTEM}, {"role": "user", "content": f"""
Rakip ve pazar istihbaratı sentezi. Bölge: {ad}. Tema: {tema}.
L'CARLIÉ ürünleri: {urunler}
<veri>
{_kanit_blogu(kanitlar, 12000)}
</veri>
Yalnız veride geçen marka ve olgulara dayan. JSON:
{{"rakip_kartlari": [{{"marka": "...", "ne_yapiyor": "somut (ürün, mesaj, fiyat, kanal)", "nasil_one_cikiyor": "...", "kanit": ["K1"]}}],
  "bizde_eksik": [{{"baslik": "...", "neden_onemli": "...", "onem": 1-5, "kanit": ["K2"]}}],
  "firsatlar": [{{"baslik": "eylem fiiliyle", "ilgili_departman": "şu kodlardan biri: {dep_kodlari}",
      "tip": "ARASTIRMA|ANALIZ|TASLAK|ONAY_GEREKTIREN", "cikti": "...", "kabul_olcutu": "...",
      "erisim": 1-10, "etki": 0.25|0.5|1|2|3, "guven": 0.5|0.8|1, "efor_gun": 1-30}}],
  "yeni_arastirma_sorulari": ["Türkçe, kurum/kanal adı içeren somut arama konusu"],
  "ozet": "3-4 cümle: bu bölgede bu temada ne oluyor ve bizim için anlamı"}}
En çok 6 kart, 5 eksik, 4 fırsat, 2 soru."""}], "rakip-sentez")
        gecerli = {k.kimlik for k in kanitlar}
        kaynak = {k.kimlik: k.kaynak for k in kanitlar}
        kartlar = []
        for c in (v.get("rakip_kartlari") or [])[:6]:
            if not isinstance(c, dict):
                continue
            kn = _kanit_listesi(c.get("kanit"), gecerli)
            if not kn:
                continue   # kaynaksız rakip kartı yok
            kartlar.append({"tarih": tarih, "bolge": kod, "tema": tema, "marka": temizle(c.get("marka"), 80),
                            "ne_yapiyor": temizle(c.get("ne_yapiyor"), 500),
                            "nasil_one_cikiyor": temizle(c.get("nasil_one_cikiyor"), 400),
                            "kaynaklar": [kaynak[x] for x in kn]})
        eksikler = []
        for e in (v.get("bizde_eksik") or [])[:5]:
            if isinstance(e, dict) and len(temizle(e.get("baslik"), 160)) > 5:
                kn = _kanit_listesi(e.get("kanit"), gecerli)
                eksikler.append({"tarih": tarih, "bolge": kod, "baslik": temizle(e.get("baslik"), 160),
                                 "neden": temizle(e.get("neden_onemli"), 400), "onem": e.get("onem"),
                                 "kaynaklar": [kaynak[x] for x in kn], "dogrulandi": bool(kn)})
        agac = self.iu.agac_deposu.oku()
        hedef_ids = {str(h.get("id")) for h in agac["hedefler"]}
        gorevler = []
        for n, f in enumerate((v.get("firsatlar") or [])[:4]):
            if not isinstance(f, dict):
                continue
            dkod = str(f.get("ilgili_departman") or "")
            dep = deps.get(dkod) or deps.get(_kod_bul(deps, ("COMPETITOR_INT", "MARKET_INT")) or "")
            if not dep or not dep.uyeler:
                continue
            g = gorev_dogrula(dict(f, sure_gun=f.get("efor_gun")), dep, hedef_ids)
            if not g:
                continue
            try:
                rice = float(f.get("erisim", 1)) * float(f.get("etki", 0.5)) * float(f.get("guven", 0.5)) / max(1.0, float(f.get("efor_gun", 5)))
            except (TypeError, ValueError):
                rice = 0.0
            g["neden"] = f"Rakip istihbaratı {kod}/{tema}. RICE {rice:.2f}"
            x = self.iu._gorev_ekle(agac, dep, g, "rakip", tarih, n + 1 + (10 if self.o.saat().hour >= 10 else 0))
            if x:
                x["rice"] = round(rice, 2)
                gorevler.append(x)
        if not self.iu.kuru:
            self.iu.agac_deposu.yaz(agac, self.o.saat())
        rk = _kod_bul(deps, ("COMPETITOR_INT", "MARKET_INT"))
        for s in (v.get("yeni_arastirma_sorulari") or [])[:2]:
            if rk:
                self._plan_ekle(rk, s, f"rakip istihbaratı {kod}/{tema} sentezinden doğdu ({tarih})")
        self.iu._ofis(uye, "COMPLETED", f"Rakip taraması bitti: {ad} · {len(kartlar)} kart")
        self._ekle_jsonl("rakip", "kartlar.jsonl", kartlar)
        self._ekle_jsonl("rakip", "eksikler.jsonl", eksikler)
        md = [f"# Rakip istihbaratı — {ad} · {tema} · {tarih}", "", temizle(v.get("ozet"), 1200), "", "## Rakip kartları"]
        for c in kartlar:
            md += [f"### {c['marka']}", f"- Ne yapıyor: {c['ne_yapiyor']}", f"- Nasıl öne çıkıyor: {c['nasil_one_cikiyor']}",
                   "- Kaynak: " + "; ".join(c["kaynaklar"])]
        md += ["", "## Bizde eksik olan"] + [f"- **{e['baslik']}** (önem {e['onem']}) — {e['neden']}" + ("" if e["dogrulandi"] else " _(DOĞRULANMADI)_") for e in eksikler]
        md += ["", "## Fırsatlar → görev"] + [f"- {g['baslik']} · {g['tip']} · RICE {g.get('rice')} · `{g['sorumlu']}`" for g in gorevler]
        yol = self._yaz("rakip", f"{tarih}-{kod}-{self._sira(len(TEMALAR), 'tema')}.md", "\n".join(md))
        return {"mod": "rakip", "tarih": tarih, "bolge": kod, "tema": tema, "kanit": len(kanitlar),
                "kart": len(kartlar), "eksik": len(eksikler), "gorev": len(gorevler), "rapor": yol, "kayit": self.iu.kayit}

    # ------------------------------------------------------------ kreatif
    def kreatif(self) -> dict:
        tarih = self._gun()
        deps = self._deps()
        urunler = self.o.urunler() if self.o.urunler else []
        if not urunler:
            return {"mod": "kreatif", "hata": "ürün listesi yok", "kayit": self.iu.kayit}
        urun, bilgi = urunler[self._sira(len(urunler), "urun")]
        kk = _kod_bul(deps, ("CREATIVE", "TASARIM", "DESIGN", "CREATIVE_STRAT"))
        kuye = deps[kk].uyeler[0].key if kk and deps[kk].uyeler else ""
        self.iu._ofis(kuye, "WORKING", f"{urun} için bilimsel kaynak tarıyor ve bilgi kartı yazıyor")
        kurallar = self.o.bilgi_dosyasi("10-iddia-kurallari") if self.o.bilgi_dosyasi else ""
        marka = self.o.bilgi_dosyasi("11-marka-dili") if self.o.bilgi_dosyasi else ""
        urun_md = self.o.bilgi_dosyasi(f"30-urun-{urun.split()[0].lower()}") if self.o.bilgi_dosyasi else ""
        plan = self._model("kreatif_sorgu", [{"role": "system", "content": SISTEM}, {"role": "user", "content": f"""
Ürün: {urun}
<veri>
{(bilgi + chr(10) + urun_md)[:5000]}
</veri>
Bu ürünün formülündeki en ilginç 3 bileşen veya tasarım kararı için bilimsel kaynak arayacağız.
JSON: {{"odaklar": [{{"konu": "bileşen/mekanizma (Türkçe)", "pubmed": "English PubMed query, 3-6 words", "web": "Türkçe veya İngilizce şaşırtıcı-ama-doğru bilgi araması"}}]}}"""}], "kreatif-sorgu")
        kanitlar: list[Kanit] = [Kanit("", f"ürün-bilgisi:{urun}", (bilgi + "\n" + urun_md)[:3000])]
        for od in (plan.get("odaklar") or [])[:3]:
            if not isinstance(od, dict):
                continue
            if self.o.pubmed and od.get("pubmed"):
                try:
                    kanitlar += self.o.pubmed(temizle(od.get("pubmed"), 120))[:4]
                except Exception as e:  # noqa: BLE001
                    self.iu.kayit.append({"pubmed": str(od.get("pubmed"))[:60], "uyari": str(e)[:150]})
            if self.o.grounded and od.get("web") and self.iu.butce.kalan(tarih) > 0:
                try:
                    metin, urller = self.o.grounded(temizle(od.get("web"), 200))
                    self.iu.butce.harca(tarih)
                    if metin:
                        kanitlar.append(Kanit("", "web-özet:" + (urller[0] if urller else "kaynaksız"), metin[:2000]))
                except Exception as e:  # noqa: BLE001
                    self.iu.kayit.append({"web": str(od.get("web"))[:60], "uyari": str(e)[:150]})
        kanitlar = [Kanit(f"K{i+1}", k.kaynak, k.metin) for i, k in enumerate(kanitlar)]
        v = self._model("kreatif", [{"role": "system", "content": SISTEM}, {"role": "user", "content": f"""
Kreatif bilgi hattı. Ürün: {urun}
Hedef: insanların "bunu bilmiyordum" diyeceği, GERÇEKTEN bilgi veren içerik.
YASAK örnek (sığ, bariz): "BABY RESCUE çantada kolay taşınır çünkü 5 ml." Ambalaj boyu, "pratik",
"her cilde uygun", "doğal ve etkili" gibi bariz/boş cümleler REDDEDİLİR.
İSTENEN: mekanizma (cilt bariyeri, pH, lipid, mikrobiyom, bileşenin kaynağı ve tarihi, neden bu
konsantrasyon/neden bu taban), şaşırtıcı ama kaynaklı bir gerçek, yaygın bir yanlışın düzeltilmesi.
Bileşen hakkındaki bilimsel bulgu ÜRÜN İDDİASI gibi sunulamaz (AB 655/2013, TİTCK iddia kılavuzu).
İddia kuralları:
{kurallar[:2500]}
Marka dili:
{marka[:1500]}
<veri>
{_kanit_blogu(kanitlar, 11000)}
</veri>
JSON: {{"kartlar": [{{"baslik": "...", "kanca": "merak uyandıran ilk cümle", "bilgi": "4-6 cümle, mekanizma ve bağlam",
   "neden_sasirtici": "...", "yaygin_yanlis": "varsa düzeltilen yanlış", "kaynak": ["K2"],
   "urune_baglanti": "iddiasız köprü: 'formülümüzde X bulunur' düzeyinde",
   "format": "carousel|reels|blog|eczaci_egitim_notu",
   "gorsel_brif": {{"metafor": "...", "sahne": "...", "metin_katmani": ["slayt 1 metni", "..."],
      "ton_renk": "...", "istem_en": "AI görsel istemi (İngilizce; ürün ambalajı ve yazı ÜRETTİRİLMEZ)", "negatif": "..."}}}}]}}
Tam 3 kart."""}], "kreatif-uret")
        gecerli = {k.kimlik for k in kanitlar}
        kaynak = {k.kimlik: k.kaynak for k in kanitlar}
        adaylar = []
        for c in (v.get("kartlar") or [])[:3]:
            if not isinstance(c, dict):
                continue
            kn = [x for x in _kanit_listesi(c.get("kaynak"), gecerli) if not kaynak[x].startswith("ürün-bilgisi")]
            if not kn:
                self.iu.kayit.append({"kart": temizle(c.get("baslik"), 80), "ret": "dış kaynak yok"})
                continue
            adaylar.append((c, kn))
        gecen = []
        for c, kn in adaylar:
            ozet = json.dumps({k: c.get(k) for k in ("baslik", "kanca", "bilgi", "neden_sasirtici", "yaygin_yanlis", "urune_baglanti")}, ensure_ascii=False)
            h = self._model("hakem", [{"role": "system", "content": "Sen kozmetik içerik editörü ve mevzuat hakemisin. Yalnız JSON döndür."},
                                      {"role": "user", "content": f"""Bu içerik kartını puanla.
<kart>{ozet[:3000]}</kart>
<kaynaklar>{_kanit_blogu([k for k in kanitlar if k.kimlik in kn], 4000)}</kaynaklar>
Ölçütler: (1) bilgi_degeri 1-5: sıradan bir tüketici yeni ve doğru bir şey öğrenir mi? Ambalaj boyu/pratiklik
gibi bariz bilgi = 1. (2) kaynakla_tutarli: true/false. (3) mevzuat: bileşen bulgusu ürün iddiası gibi
sunulmuş mu, tedavi/iyileştirme iddiası var mı, yanıltıcı mı (AB 655/2013 6 kriter). (4) karar.
JSON: {{"bilgi_degeri": 1-5, "kaynakla_tutarli": true, "mevzuat_sorunu": "yoksa boş", "karar": "GECTI|REDDET", "gerekce": "..."}}"""}], "kreatif-hakem")
            try:
                deger = int(h.get("bilgi_degeri") or 0)
            except (TypeError, ValueError):
                deger = 0
            ok = h.get("karar") == "GECTI" and deger >= 4 and h.get("kaynakla_tutarli") is True and not str(h.get("mevzuat_sorunu") or "").strip()
            kayit = {"tarih": tarih, "urun": urun, "baslik": temizle(c.get("baslik"), 160), "kanca": temizle(c.get("kanca"), 300),
                     "bilgi": temizle(c.get("bilgi"), 1500), "neden_sasirtici": temizle(c.get("neden_sasirtici"), 400),
                     "yaygin_yanlis": temizle(c.get("yaygin_yanlis"), 400), "urune_baglanti": temizle(c.get("urune_baglanti"), 300),
                     "format": temizle(c.get("format"), 40), "kaynaklar": [kaynak[x] for x in kn],
                     "gorsel_brif": {k: (temizle(val, 600) if not isinstance(val, list) else [temizle(z, 200) for z in val[:8]])
                                     for k, val in (c.get("gorsel_brif") or {}).items()} if isinstance(c.get("gorsel_brif"), dict) else {},
                     "hakem": {"bilgi_degeri": deger, "karar": "GECTI" if ok else "REDDET",
                               "gerekce": temizle(h.get("gerekce"), 400), "mevzuat": temizle(h.get("mevzuat_sorunu"), 300),
                               "model": (h.get("_model") or {}).get("provider")}}
            self._ekle_jsonl("kreatif", "tum-kartlar.jsonl", [kayit])
            if ok:
                gecen.append(kayit)
        self.iu._ofis(kuye, "COMPLETED", f"{urun}: {len(gecen)} kart hakemden geçti")
        agac = self.iu.agac_deposu.oku()
        ajans = deps.get(_kod_bul(deps, ("CREATIVE", "TASARIM", "DESIGN", "CREATIVE_STRAT")) or "")
        gorev = 0
        for n, k in enumerate(gecen):
            ad = re.sub(r"\W+", "-", f"{tarih}-{urun}-{n+1}").strip("-")[:80]
            b = k["gorsel_brif"]
            md = [f"# {k['baslik']}", f"_Ürün: {urun} · {k['format']} · hakem bilgi değeri {k['hakem']['bilgi_degeri']}/5_", "",
                  f"**Kanca:** {k['kanca']}", "", k["bilgi"], "", f"**Neden şaşırtıcı:** {k['neden_sasirtici']}",
                  f"**Düzeltilen yanlış:** {k['yaygin_yanlis']}" if k["yaygin_yanlis"] else "",
                  f"**Ürüne köprü (iddiasız):** {k['urune_baglanti']}", "", "## Kaynaklar"] + [f"- {s}" for s in k["kaynaklar"]] + [
                  "", "## Görsel brif (ajans)", f"- Metafor: {b.get('metafor', '')}", f"- Sahne: {b.get('sahne', '')}",
                  f"- Ton/renk: {b.get('ton_renk', '')}", "- Metin katmanı:"] + [f"  - {s}" for s in (b.get("metin_katmani") or [])] + [
                  f"- AI istemi: `{b.get('istem_en', '')}`", f"- Negatif: `{b.get('negatif', '')}`", "",
                  f"_Hakem: {k['hakem']['gerekce']}_"]
            yol = self._yaz("kreatif/kartlar", ad + ".md", "\n".join(x for x in md if x is not None))
            k["yol"] = yol
            if ajans and ajans.uyeler:
                g = gorev_dogrula({"baslik": f"Görsel üret: {k['baslik']}"[:150], "tip": "ONAY_GEREKTIREN",
                                   "cikti": f"{k['format']} görselleri ({yol})", "kabul_olcutu": "brifteki metafor ve metin katmanı; ambalaj/yazı AI'ya üretilmez",
                                   "sure_gun": 3, "neden": f"Kreatif bilgi kartı hakemden {k['hakem']['bilgi_degeri']}/5 ile geçti"}, ajans, set())
                if g and self.iu._gorev_ekle(agac, ajans, g, "kreatif", tarih, n + 1 + (10 if self.o.saat().hour >= 13 else 0)):
                    gorev += 1
        if not self.iu.kuru:
            kdep = agac["departmanlar"].setdefault("ICERIK_KUTUPHANESI", {"ad": "İçerik kütüphanesi", "gorevler": [], "raporlar": [], "fikirler": []})
            kdep.setdefault("kartlar", [])
            kdep["kartlar"] = (kdep["kartlar"] + [{"tarih": tarih, "urun": urun, "baslik": k["baslik"], "yol": k.get("yol")} for k in gecen])[-200:]
            self.iu.agac_deposu.yaz(agac, self.o.saat())
        return {"mod": "kreatif", "tarih": tarih, "urun": urun, "kanit": len(kanitlar), "aday": len(adaylar),
                "hakemden_gecen": len(gecen), "gorsel_gorevi": gorev, "kayit": self.iu.kayit}

    # ------------------------------------------------------------ b2b
    def b2b(self) -> dict:
        tarih = self._gun()
        deps = self._deps()
        ozet = self.o.b2b_ozet() if self.o.b2b_ozet else {}
        if not ozet:
            return {"mod": "b2b", "hata": "b2b verisi yok", "kayit": self.iu.kayit}
        bdep = deps.get(_kod_bul(deps, ("PHARMACY", "B2B", "FIELD_B2B", "BIZDEV")) or "")
        hedef_ids = {str(h.get("id")) for h in self.iu.agac_deposu.oku()["hedefler"]}
        kurallar = self.o.bilgi_dosyasi("10-iddia-kurallari") if self.o.bilgi_dosyasi else ""  # noqa: F841
        urunler = ", ".join(u for u, _ in (self.o.urunler() if self.o.urunler else [])[:30])
        v = self._model("b2b", [{"role": "system", "content": SISTEM}, {"role": "user", "content": f"""
B2B eczane programı. L'CARLIÉ eczanelere toptan satış kanalı kuruyor. Ürünler: {urunler}
Aşağıdaki veri YALNIZ TOPLAMLARDIR (kişi verisi yok).
<veri>
{json.dumps(ozet, ensure_ascii=False)[:9000]}
</veri>
Hukuki çerçeve (veri değil, kural): 6563 s. Kanun m.6/2 tacir/esnafa önceden onaysız ticari ileti
mümkün ama gönderim öncesi İYS kaydı ve ret kontrolü zorunlu; her iletide ret yolu. Kişisel
(ad.soyad@) adresler ve üçüncü kişiden alınmış listelerle toplu pazarlama KVKK riski taşır;
ilk temasta aydınlatma. Eczacılar ilaç marjı düştüğü için dermokozmetiğe yöneliyor. Dağıtım
çoğunlukla ecza depoları (Selçuk ~%40 pay, Alliance Healthcare) üzerinden.
Bu haftanın B2B planını yaz. JSON:
{{"il_onceligi": [{{"il": "...", "neden": "veriden", "ilk_hedef_eczane": 0, "yontem": "depo/saha/çevrim içi"}}],
  "segmentler": [{{"ad": "...", "tanim": "...", "yaklasim": "..."}}],
  "depo_stratejisi": "...",
  "satis_kiti": [{{"baslik": "eczacıya tek sayfa/eğitim notu/kampanya", "icerik_ozeti": "..."}}],
  "uyum_adimlari": ["İYS, aydınlatma, kaynak beyanı..."],
  "gorevler": [{{"baslik": "...", "tip": "ARASTIRMA|ANALIZ|TASLAK|VERI_BAGLANTISI|ONAY_GEREKTIREN", "sorumlu": "",
      "cikti": "...", "kabul_olcutu": "...", "sure_gun": 5}}],
  "ozet": "3-4 cümle"}}
En çok 8 il, 4 segment, 4 kit, 5 görev. Toplu e-posta/arama gönderimi her zaman ONAY_GEREKTIREN."""}], "b2b-plan")
        agac = self.iu.agac_deposu.oku()
        gorevler = []
        if bdep and bdep.uyeler:
            for n, g in enumerate((v.get("gorevler") or [])[:5]):
                gg = gorev_dogrula(g, bdep, hedef_ids)
                if gg and re.search(r"(?i)gönder|toplu|e-?posta at|mail at|whatsapp|sms|telefonla ara|aranacak", gg["baslik"]):
                    gg["tip"] = "ONAY_GEREKTIREN"   # dışarıya temas her zaman sahip onayında
                if gg:
                    x = self.iu._gorev_ekle(agac, bdep, gg, "b2b", tarih, n + 1)
                    if x:
                        gorevler.append(x)
        if not self.iu.kuru:
            self.iu.agac_deposu.yaz(agac, self.o.saat())
        md = [f"# B2B eczane programı — {tarih}", "", temizle(v.get("ozet"), 1200), "",
              "## Kaynak veri (toplam)", "```", json.dumps({k: ozet[k] for k in list(ozet)[:6]}, ensure_ascii=False, indent=1)[:2500], "```",
              "", "## İl önceliği"] + [f"- **{temizle(i.get('il'), 40)}** — {temizle(i.get('neden'), 300)} · ilk hedef {i.get('ilk_hedef_eczane')} · {temizle(i.get('yontem'), 100)}"
                                       for i in (v.get("il_onceligi") or [])[:8] if isinstance(i, dict)]
        md += ["", "## Segmentler"] + [f"- **{temizle(s.get('ad'), 80)}**: {temizle(s.get('tanim'), 300)} → {temizle(s.get('yaklasim'), 300)}"
                                        for s in (v.get("segmentler") or [])[:4] if isinstance(s, dict)]
        md += ["", "## Depo stratejisi", temizle(v.get("depo_stratejisi"), 1200), "", "## Satış kiti taslakları"]
        md += [f"- **{temizle(s.get('baslik'), 120)}**: {temizle(s.get('icerik_ozeti'), 600)}" for s in (v.get("satis_kiti") or [])[:4] if isinstance(s, dict)]
        md += ["", "## Uyum adımları"] + [f"- {temizle(x, 300)}" for x in (v.get("uyum_adimlari") or [])[:8]]
        md += ["", "## Görevler"] + [f"- {g['baslik']} · {g['tip']} · `{g['sorumlu']}`" for g in gorevler]
        if self.o.b2b_liste and not self.iu.kuru:
            try:
                md += ["", f"_Kişi verili öncelik listesi yalnız sunucuda: {self.o.b2b_liste()}_"]
            except Exception as e:  # noqa: BLE001
                self.iu.kayit.append({"b2b_liste": str(e)[:200]})
        yol = self._yaz("b2b", f"{tarih}-plan.md", "\n".join(md))
        return {"mod": "b2b", "tarih": tarih, "gorev": len(gorevler), "rapor": yol, "kayit": self.iu.kayit}

    # ------------------------------------------------------------ retro
    def retro(self, sinir: int = 60) -> dict:
        tarih = self._gun()
        deps = self._deps()
        agac = self.iu.agac_deposu.oku()
        rapor = konu = 0
        for kod, d in list(agac["departmanlar"].items())[:sinir]:
            dep = deps.get(kod)
            if not dep or not dep.uyeler:
                continue
            if d.get("retro", {}).get("tarih") == tarih:
                continue
            g = d.get("gorevler", [])[-25:]
            if not g:
                continue
            satir = []
            for x in g:
                t = x.get("teslim") or {}
                satir.append(f"- [{x.get('durum')}] {x.get('baslik')} ({x.get('tip')})" +
                             (f" — kalite: {t.get('kalite')} {'; '.join(t.get('sebepler') or [])[:200]}" if t else ""))
            self.iu._ofis(dep.uyeler[0].key, "WORKING", f"{dep.ad}: haftalık retro")
            v = self._model("retro", [{"role": "system", "content": SISTEM}, {"role": "user", "content": f"""
Haftalık ekip retrosu. Departman: {dep.kod} — {dep.ad}. Misyon: {dep.misyon[:300]}
Son görevler ve sonuçları:
{chr(10).join(satir)}
Önceki odak: {d.get('retro', {}).get('odak', '(yok)')}
Dürüst değerlendir. JSON:
{{"degerlendirme": "2-3 cümle", "ise_yarayan": ["..."], "ise_yaramayan": ["..."],
  "kok_neden": "kalite kapısından düşen/bekleyen işlerin asıl nedeni (veri eksikliği, yanlış görev tanımı, yetki...)",
  "sahipten_istek": "bu ekibin sahipten tek somut ihtiyacı (veri bağlantısı, karar, erişim) veya boş",
  "odak": "gelecek haftanın tek cümlelik odağı",
  "yeni_konular": ["dışarıda araştırılacak somut konu (kurum/kanal adı içersin)", "..."]}}"""}], "retro")
            d["retro"] = {"tarih": tarih, "odak": temizle(v.get("odak"), 300), "kok_neden": temizle(v.get("kok_neden"), 400),
                          "sahipten_istek": temizle(v.get("sahipten_istek"), 300), "degerlendirme": temizle(v.get("degerlendirme"), 600)}
            md = [f"# Retro — {dep.ad} ({kod}) · {tarih}", "", d["retro"]["degerlendirme"], "",
                  "## İşe yarayan"] + [f"- {temizle(x, 300)}" for x in (v.get("ise_yarayan") or [])[:5]] + [
                  "", "## İşe yaramayan"] + [f"- {temizle(x, 300)}" for x in (v.get("ise_yaramayan") or [])[:5]] + [
                  "", f"**Kök neden:** {d['retro']['kok_neden']}", f"**Sahipten istek:** {d['retro']['sahipten_istek']}",
                  f"**Gelecek hafta odağı:** {d['retro']['odak']}", "", "## Yeni araştırma konuları"]
            for k in (v.get("yeni_konular") or [])[:2]:
                if len(temizle(k, 180)) > 8:
                    md.append(f"- {temizle(k, 180)}")
                    if self._plan_ekle(kod, k, f"{tarih} retrosu: {d['retro']['kok_neden'][:150]}"):
                        konu += 1
            d.setdefault("raporlar", []).append({"tarih": tarih, "tur": "retro", "yol": self._yaz("retro", f"{tarih}-{kod}.md", "\n".join(md))})
            rapor += 1
        if not self.iu.kuru:
            self.iu.agac_deposu.yaz(agac, self.o.saat())
        return {"mod": "retro", "tarih": tarih, "rapor": rapor, "yeni_konu": konu, "kayit": self.iu.kayit}
