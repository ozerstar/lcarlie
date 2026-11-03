"""Karar kurulu: üretilen sonuçları denetler, sorgular, karara bağlar ve dağıtır.

NEDEN VAR
Sahip 03.11.2026: "Çıkan sonuçları denetleyecek ekipler var, onlara gönder;
rakip analizlerini değerlendiren ekipler olmalı, red team sorgulamalı, ana
kafa uygun işleri yürütmeli, orchestrator herkese dağıtmalı; karar için
asistan ve Jarvis'e göster." Ölçüm: teslimler, rakip kartları ve Radar
sabah özeti yalnız dosyaya yazılıyordu; kimse okumuyordu. İş üreticinin 63
ONAY_GEREKTIREN işi gerçek onay kuyruğuna (ana sayfa "Onay bekleyen")
hiç gitmemişti: ana sayfa 0 gösteriyordu.

AKIŞ (koşu başına 3 adım, model çağrısı = denetçi birim sayısı + 2)
  1 DENETİM   Her sonuç kendi denetçi birimine gider (DENETCI haritası).
              Birim: ne anlama geliyor, güven, en çok 2 iç öneri.
  2 RED TEAM  Bütün öneriler toplu sorgulanır: KABUL / SORGULA / RED.
  3 ANA KARAR EXEC (ana kafa) RED olmayanları YAP / BEKLET / IPTAL eder.
  Dağıtım     YAP + iç iş  -> hedef birime görev (kaynak=kurul), yurut yapar.
              YAP + onay   -> core.ai_sistem_onerisi -> ana sayfa onay kuyruğu.
  Rapor       raporlar/<tarih>/KURUL-<saat>.md (panelde Raporlar).

🔴 SINIRLAR
  - Dış eylem YOK. Onay isteyen iş yalnız REQUEST_HUMAN_REVIEW önerisidir;
    sahip onaylasa bile hiçbir platforma yazılmaz.
  - Koşu başına en çok GOREV_TAVAN iç görev ve ONAY_TAVAN onay önerisi.
  - Model çıktısındaki kimlikler (S1, O1...) yalnız bizim verdiklerimizden
    kabul edilir; uydurulan kimlik ve departman atılır.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .is_uretici import SISTEM, Departman, IsUretici, temizle

KADEME = {"kurul_denetim": "hizli", "kurul_redteam": "muhakeme", "kurul_karar": "muhakeme"}
TOKEN = {"kurul_denetim": 2200, "kurul_redteam": 2400, "kurul_karar": 2600}
GOREV_TAVAN = 8
ONAY_TAVAN = 3
SONUC_TAVAN = 18          # koşu başına denetlenen sonuç
ESKI_ONAY_TAVAN = 10      # koşu başına ele alınan birikmiş ONAY_BEKLIYOR işi
IC_TIPLER = ("ARASTIRMA", "ANALIZ", "TASLAK")

# Sonucu üreten birim -> onu denetleyen birim. Yoksa EXEC denetler.
DENETCI = {
    "META_MEDIA": "DATA_BI", "DATA_BI": "FINANCE", "COPY": "CREATIVE_STRAT", "ART": "CREATIVE_STRAT",
    "UGC": "CREATIVE_STRAT", "TASARIM": "BRAND", "INSTAGRAM": "BRAND", "SOCIAL": "BRAND",
    "CONTENT": "BRAND", "YAYIN": "REGULATORY", "SEO": "WEB", "CRO": "WEB", "WEB": "CRO",
    "ECOM": "FINANCE", "MARKETPLACE": "FINANCE", "PRODUCT": "FINANCE", "FINANCE": "EXEC",
    "CS": "QUALITY", "CRM": "RETENTION", "RETENTION": "CRM", "CUSTOMER_INT": "PRODUCT",
    "QUALITY": "PRODUCT", "COMPETITOR_INT": "MARKET_INT", "MARKET_INT": "CREATIVE_STRAT",
    "BRAND": "REGULATORY", "REGULATORY": "LEGAL", "FULFILLMENT": "ECOM",
    "RND": "PRODUCT", "EXPERIMENT": "DATA_BI", "CREATIVE_STRAT": "META_MEDIA",
    # Dış istihbarat iki taraftan okunur: pazar anlamı + kreatif karşılığı.
    "_RAKIP": "COMPETITOR_INT", "_RADAR": "MARKET_INT",
}


def _simdi_tr(saat: datetime) -> datetime:
    return saat.astimezone(timezone(timedelta(hours=3)))


def _liste(v: Any) -> list:
    return v if isinstance(v, list) else []


class Kurul:
    def __init__(self, iu: IsUretici, radar_panel: Path | None = None):
        self.iu = iu
        self.o = iu.o
        self.radar_panel = radar_panel
        self.programlar = iu.dizin.parent / "programlar"

    # ------------------------------------------------------------ yardımcı
    def _model(self, tur: str, kullanici: str, anahtar: str) -> dict:
        from . import is_uretici as m
        m.KADEME.setdefault(tur, KADEME[tur])
        m.MAX_TOKENS.setdefault(tur, TOKEN[tur])
        return self.iu._model(tur, [{"role": "system", "content": SISTEM},
                                    {"role": "user", "content": kullanici}], anahtar)

    def _denetci(self, kaynak_dep: str, deps: dict[str, Departman]) -> str:
        d = DENETCI.get(kaynak_dep, "EXEC")
        if d not in deps or not deps[d].uyeler:
            d = "EXEC" if "EXEC" in deps and deps["EXEC"].uyeler else kaynak_dep
        return d

    # ------------------------------------------------------------ girdiler
    def sonuclar(self, agac: dict, simdi: datetime) -> list[dict]:
        """Denetlenmemiş sonuçlar: son 36 saatin teslimleri + bugünün rakip raporları + Radar özeti."""
        out: list[dict] = []
        sinir = simdi - timedelta(hours=36)
        for kod, d in agac["departmanlar"].items():
            for g in d.get("gorevler", []):
                t = g.get("teslim") or {}
                if t.get("kalite") not in ("GECTI", "KISMI") or g.get("kurul"):
                    continue
                try:
                    if datetime.fromisoformat(str(t.get("tarih"))) < sinir:
                        continue
                except ValueError:
                    continue
                metin = t.get("ozet") or ""
                try:
                    metin = Path(t["yol"]).read_text(encoding="utf-8")[:2500]
                except Exception:  # noqa: BLE001, S110 - özet yeter
                    pass
                out.append({"tur": "teslim", "ref": g["id"], "dep": kod, "baslik": g.get("baslik", ""),
                            "metin": metin, "gorev": g})
        gun = _simdi_tr(simdi).date().isoformat()
        islenen = set(agac.setdefault("kurul", {}).get("islenen", []))
        for yol in sorted((self.programlar / "rakip").glob(f"{gun}-*.md")):
            if yol.name in islenen:
                continue
            out.append({"tur": "rakip", "ref": yol.name, "dep": "_RAKIP", "baslik": f"Rakip istihbaratı {yol.stem}",
                        "metin": yol.read_text(encoding="utf-8")[:3000]})
        if self.radar_panel and self.radar_panel.exists():
            try:
                p = json.loads(self.radar_panel.read_text(encoding="utf-8"))
                oz = p.get("sabah_ozeti") or {}
                ref = f"radar-{oz.get('tarih') or gun}"
                if oz and ref not in islenen:
                    out.append({"tur": "radar", "ref": ref, "dep": "_RADAR", "baslik": "Radar sabah özeti",
                                "metin": json.dumps(oz, ensure_ascii=False)[:3000]})
            except Exception as e:  # noqa: BLE001
                self.iu.kayit.append({"kurul": "radar", "uyari": f"radar özeti okunamadı: {e}"[:200]})
        return out[:SONUC_TAVAN]

    # ------------------------------------------------------------ adımlar
    def denetle(self, dep: Departman, kalemler: list[dict], deps: dict[str, Departman]) -> list[dict]:
        bloklar = "\n\n".join(f"[S{i + 1}] ({k['tur']} · üreten: {k['dep'].strip('_')}) {k['baslik']}\n{k['metin']}"
                              for i, k in enumerate(kalemler))
        kodlar = ", ".join(sorted(k for k, d in deps.items() if d.uyeler))
        v = self._model("kurul_denetim", f"""Denetçi birim: {dep.kod} — {dep.ad}. Misyon: {dep.misyon or '-'}
Aşağıdaki sonuçlar başka ekiplerden geldi; senin işin onları DENETLEMEK ve şirket için anlamını çıkarmak.
<veri>
{bloklar}
</veri>
Her sonuç için: güvenilir mi (rakamlar kendi içinde tutarlı mı, kaynak var mı), bizim için ne anlama geliyor,
somut olarak ne yapılmalı. Öneri departmanı yalnız şu kodlardan biri olabilir: {kodlar}.
Dış dünyada eylem (yayın, mesaj, fiyat, reklam, sipariş) gerektiren öneri tip=ONAY_GEREKTIREN olmalı.
JSON: {{"denetimler": [{{"kimlik": "S1", "guven": "YUKSEK|ORTA|DUSUK", "sorun": "varsa tutarsızlık/eksik kaynak",
  "anlam": "1-2 cümle", "oneriler": [{{"baslik": "eylem fiiliyle", "tip": "ARASTIRMA|ANALIZ|TASLAK|ONAY_GEREKTIREN",
  "departman": "KOD", "neden": "hangi bulgudan"}}]}}]}}
Her sonuç için en çok 2 öneri; gereksizse boş liste.""", "kurul-denetim")
        out = []
        for d in _liste(v.get("denetimler")):
            if not isinstance(d, dict):
                continue
            try:
                i = int(str(d.get("kimlik", "")).lstrip("S")) - 1
            except ValueError:
                continue
            if not 0 <= i < len(kalemler):
                continue
            oneriler = []
            for o in _liste(d.get("oneriler"))[:2]:
                if not isinstance(o, dict):
                    continue
                hedef = str(o.get("departman") or "").strip().upper()
                baslik = temizle(o.get("baslik"), 160)
                if hedef not in deps or not deps[hedef].uyeler or len(baslik) < 6:
                    continue
                tip = str(o.get("tip") or "ANALIZ").upper()
                oneriler.append({"baslik": baslik, "tip": tip if tip in (*IC_TIPLER, "ONAY_GEREKTIREN") else "ANALIZ",
                                 "departman": hedef, "neden": temizle(o.get("neden"), 300)})
            guven = str(d.get("guven") or "").upper()
            out.append({"kalem": kalemler[i], "denetci": dep.kod,
                        "guven": guven if guven in ("YUKSEK", "ORTA", "DUSUK") else "ORTA",
                        "sorun": temizle(d.get("sorun"), 300), "anlam": temizle(d.get("anlam"), 400),
                        "oneriler": oneriler})
        return out

    def sorgula(self, oneriler: list[dict]) -> dict[str, dict]:
        if not oneriler:
            return {}
        blok = "\n".join(f"[{o['id']}] → {o['departman']} · {o['tip']} · {o['baslik']}\n"
                         f"   dayanak: {o['dayanak']}\n   neden: {o['neden']}" for o in oneriler)
        kurallar = "\n".join(x.metin for x in self.iu._bilgi(["buyume-kurallari"], 2500))
        if kurallar:
            blok = f"[ŞİRKET KURALLARI — bilgi]\n{kurallar}\n\n[ÖNERİLER]\n{blok}"
        v = self._model("kurul_redteam", f"""Sen RED TEAM / iç denetimsin. Görevin aşağıdaki önerileri SORGULAMAK:
dayanak gerçekten bunu söylüyor mu, rakam/kaynak uydurulmuş olabilir mi, mevzuat riski var mı, zaten yapılmış
veya tekrar eden bir iş mi, maliyetine değer mi. Kolay onay verme; ama gerekçesiz de reddetme.
<veri>
{blok}
</veri>
JSON: {{"kararlar": [{{"id": "O1", "karar": "KABUL|SORGULA|RED", "itiraz": "kısa gerekçe"}}]}}""", "kurul-redteam")
        gecerli = {o["id"] for o in oneriler}
        out = {}
        for k in _liste(v.get("kararlar")):
            if isinstance(k, dict) and str(k.get("id")) in gecerli:
                karar = str(k.get("karar") or "").upper()
                out[str(k["id"])] = {"karar": karar if karar in ("KABUL", "SORGULA", "RED") else "SORGULA",
                                     "itiraz": temizle(k.get("itiraz"), 300)}
        return out

    def karar_ver(self, oneriler: list[dict], hedefler: str) -> tuple[dict[str, dict], str]:
        if not oneriler:
            return {}, ""
        blok = "\n".join(f"[{o['id']}] → {o['departman']} · {o['tip']} · {o['baslik']}\n"
                         f"   dayanak: {o['dayanak']}\n   red team: {o['rt']['karar']} — {o['rt']['itiraz']}"
                         for o in oneriler)
        v = self._model("kurul_karar", f"""Sen L'CARLIÉ'nin yönetim kuruluna bağlı ana karar vericisisin (EXEC).
Şirket hedefleri:
{hedefler}
Denetçi birimlerden ve red team'den geçen öneriler:
<veri>
{blok}
</veri>
Her öneri için karar ver: YAP (bu hafta yapılsın), BEKLET (şimdi değil), IPTAL. Red team SORGULA dediyse
itirazı gidermeden YAP deme. En fazla {GOREV_TAVAN} iç iş ve {ONAY_TAVAN} sahip onayı gerektiren iş seç;
en çok satış/güven etkisi olanları önce al.
JSON: {{"kararlar": [{{"id": "O1", "karar": "YAP|BEKLET|IPTAL", "oncelik": 1, "gerekce": "kısa"}}],
 "gunun_ozeti": "sahibe 3-5 cümle: ne gördük, ne yapıyoruz, senden ne bekliyoruz"}}""", "kurul-karar")
        gecerli = {o["id"] for o in oneriler}
        out = {}
        for k in _liste(v.get("kararlar")):
            if isinstance(k, dict) and str(k.get("id")) in gecerli:
                karar = str(k.get("karar") or "").upper()
                try:
                    onc = max(1, min(3, int(k.get("oncelik") or 2)))
                except (TypeError, ValueError):
                    onc = 2
                out[str(k["id"])] = {"karar": karar if karar in ("YAP", "BEKLET", "IPTAL") else "BEKLET",
                                     "oncelik": onc, "gerekce": temizle(k.get("gerekce"), 300)}
        return out, temizle(v.get("gunun_ozeti"), 900)

    # ------------------------------------------------------------ koşu
    def calistir(self) -> dict:
        simdi = self.o.saat()
        tarih = self.iu._gun()
        agac = self.iu.agac_deposu.oku()
        deps = {d.kod: d for d in self.o.departmanlar()}
        sonuclar = self.sonuclar(agac, simdi)

        # 1) denetim: denetçi birim başına tek çağrı
        gruplar: dict[str, list[dict]] = {}
        for s in sonuclar:
            gruplar.setdefault(self._denetci(s["dep"], deps), []).append(s)
        denetimler: list[dict] = []
        for kod, kalemler in gruplar.items():
            if kod not in deps:
                continue
            self.iu._ofis(deps[kod].uyeler[0].key, "WORKING", f"{deps[kod].ad}: {len(kalemler)} sonucu denetliyor")
            try:
                denetimler += self.denetle(deps[kod], kalemler, deps)
            except RuntimeError as e:
                if "tavan" in str(e):
                    break
                self.iu.kayit.append({"kurul": kod, "hata": str(e)[:200]})
            except Exception as e:  # noqa: BLE001
                self.iu.kayit.append({"kurul": kod, "hata": str(e)[:200]})

        # öneri havuzu: denetimden gelenler + birikmiş ONAY_BEKLIYOR işler
        oneriler: list[dict] = []
        for d in denetimler:
            for o in d["oneriler"]:
                oneriler.append(dict(o, id=f"O{len(oneriler) + 1}", kaynak_ref=d["kalem"]["ref"],
                                     dayanak=f"{d['kalem']['baslik']} — denetçi {d['denetci']}: {d['anlam']}"[:500]))
        eski = [(k, g) for k, dd in agac["departmanlar"].items() for g in dd.get("gorevler", [])
                if g.get("durum") == "ONAY_BEKLIYOR"][:ESKI_ONAY_TAVAN]
        for k, g in eski:
            oneriler.append({"id": f"O{len(oneriler) + 1}", "baslik": g.get("baslik", ""), "tip": "ONAY_GEREKTIREN",
                             "departman": k, "neden": g.get("neden", ""), "eski_gorev": g,
                             "dayanak": f"birikmiş onay işi ({g.get('id')}): {g.get('cikti', '')}"[:500]})

        # 2) red team
        try:
            rt = self.sorgula(oneriler)
        except Exception as e:  # noqa: BLE001
            rt = {}
            self.iu.kayit.append({"kurul": "redteam", "hata": str(e)[:200]})
        for o in oneriler:
            o["rt"] = rt.get(o["id"], {"karar": "SORGULA", "itiraz": "red team cevap vermedi"})
        aday = [o for o in oneriler if o["rt"]["karar"] != "RED"]

        # 3) ana karar
        hedefler = "\n".join(f"- {h.get('id')}: {h.get('baslik')} ({h.get('olcut')})" for h in agac.get("hedefler", [])) or "-"
        try:
            kararlar, ozet = self.karar_ver(aday, hedefler) if rt else ({}, "")
        except Exception as e:  # noqa: BLE001
            kararlar, ozet = {}, ""
            self.iu.kayit.append({"kurul": "karar", "hata": str(e)[:200]})

        # dağıtım
        dagitilan, onaya = [], []
        for o in sorted(aday, key=lambda x: kararlar.get(x["id"], {}).get("oncelik", 9)):
            k = kararlar.get(o["id"])
            o["karar"] = k or {"karar": "BEKLET", "oncelik": 9, "gerekce": "karar verilmedi"}
            if not k or k["karar"] != "YAP":
                continue
            if o["tip"] == "ONAY_GEREKTIREN":
                if len(onaya) >= ONAY_TAVAN:
                    continue
                aid = self._onaya_gonder(o, tarih)
                if aid is not None:
                    onaya.append((o, aid))
            elif len(dagitilan) < GOREV_TAVAN:
                dep = deps[o["departman"]]
                g = {"baslik": o["baslik"], "tip": o["tip"], "sorumlu": dep.uyeler[0].key,
                     "cikti": "kurul kararı teslimi: bulgu + tablo/madde + öneri",
                     "kabul_olcutu": "dayanaktaki bulguyla ilişkisi gösterilmiş, en az 3 madde/tablo satırı",
                     "sure_gun": 3, "hedef_id": "", "neden": f"kurul: {o['dayanak']}"[:300]}
                saat = _simdi_tr(simdi).strftime("%H")
                x = self.iu._gorev_ekle(agac, dep, g, "kurul", tarih, 0,
                                        gid=f"{tarih}-{dep.kod}-kurul{saat}-{len(dagitilan) + 1}")
                if x:
                    dagitilan.append((o, x))
                    self.iu._ofis(dep.uyeler[0].key, "WORKING", f"Kuruldan iş aldı: {o['baslik']}"[:200])

        # işaretle: denetlenen sonuçlar bir daha gelmez; ele alınan eski onay işleri kapanır
        if not self.iu.kuru:
            for d in denetimler:
                kal = d["kalem"]
                if kal["tur"] == "teslim":
                    kal["gorev"]["kurul"] = {"tarih": simdi.isoformat(), "denetci": d["denetci"], "guven": d["guven"]}
                else:
                    agac["kurul"].setdefault("islenen", []).append(kal["ref"])
            agac["kurul"]["islenen"] = agac["kurul"].get("islenen", [])[-200:]
            gonderilen = {o["id"] for o, _ in onaya}
            for o in oneriler:
                g = o.get("eski_gorev")
                if g is None:
                    continue
                k = kararlar.get(o["id"], {}).get("karar")
                if o["id"] in gonderilen:
                    g["durum"] = "ONAYA_GITTI"
                elif rt.get(o["id"], {}).get("karar") == "RED" or k == "IPTAL":
                    g["durum"] = "KURUL_KAPATTI"
                elif k == "BEKLET":
                    g["durum"] = "BEKLETILDI"
                else:
                    continue   # karar yok ya da onay tavanı doldu: sonraki kurulda yeniden ele alınır
                g["kurul"] = {"tarih": simdi.isoformat(), "rt": o["rt"], "karar": o.get("karar")}

        yol = self._rapor(tarih, simdi, denetimler, oneriler, dagitilan, onaya, ozet)
        if not self.iu.kuru:
            self.iu.agac_deposu.yaz(agac, simdi)
        return {"mod": "kurul", "tarih": tarih, "sonuc": len(sonuclar), "denetim": len(denetimler),
                "oneri": len(oneriler), "red": sum(o["rt"]["karar"] == "RED" for o in oneriler),
                "gorev": len(dagitilan), "onaya": len(onaya), "rapor": yol, "kayit": self.iu.kayit}

    def _onaya_gonder(self, o: dict, tarih: str) -> int | None:
        if self.iu.kuru or not self.o.oneri_ac:
            return None
        metin = (f"KURUL KARARI · {o['departman']}\n\n{o['baslik']}\n\nDayanak: {o['dayanak']}\n"
                 f"Red team: {o['rt']['karar']} — {o['rt']['itiraz']}\nKarar: {o['karar']['gerekce']}\n\n"
                 "Onaylamak bu işi yalnız sahibin gündemine alır; hiçbir platforma otomatik yazılmaz.")
        # Aynı başlık aynı gün ikinci kez önerilmez (hash() süreçten sürece değişir; md5 sabit).
        anahtar = f"{tarih}.{o['departman']}.{hashlib.md5(o['baslik'].encode()).hexdigest()[:10]}"
        try:
            return self.o.oneri_ac(anahtar, metin[:3500],
                                   f"Kurul: denetci + red team + ana karar YAP dedi: {o['baslik']}"[:400])
        except Exception as e:  # noqa: BLE001
            self.iu.kayit.append({"kurul": "onay", "uyari": f"onay kuyruğuna yazılamadı: {e}"[:200]})
            return None

    def _rapor(self, tarih, simdi, denetimler, oneriler, dagitilan, onaya, ozet) -> str:
        saat = _simdi_tr(simdi).strftime("%H%M")
        md = [f"# Karar kurulu — {tarih} {saat[:2]}:{saat[2:]}", "",
              f"**Ana karar özeti:** {ozet or '(karar adımı çalışmadı)'}", "",
              (f"Denetlenen sonuç {len(denetimler)} · öneri {len(oneriler)} · red team reddi "
               f"{sum(o['rt']['karar'] == 'RED' for o in oneriler)} · dağıtılan görev {len(dagitilan)} · "
               f"onaya giden {len(onaya)}"), "", "## 1. Denetim"]
        for d in denetimler:
            md.append(f"- **{d['kalem']['baslik']}** ({d['kalem']['tur']}) → denetçi {d['denetci']} · güven {d['guven']}"
                      + (f" · sorun: {d['sorun']}" if d["sorun"] else "") + f"\n  - {d['anlam']}")
        md += ["", "## 2. Red team ve ana karar", "| Öneri | Birim | Red team | Karar |", "|---|---|---|---|"]
        for o in oneriler:
            k = o.get("karar") or {}
            md.append(f"| {o['baslik']} | {o['departman']} | {o['rt']['karar']}: {o['rt']['itiraz']} | "
                      f"{k.get('karar', '—')} {k.get('gerekce', '')} |".replace("\n", " "))
        md += ["", "## 3. Dağıtılan görevler"] + ([f"- {x['id']} → **{o['departman']}**: {o['baslik']}" for o, x in dagitilan]
                                               or ["- (yok)"])
        md += ["", "## 4. Sahip onayına gidenler (ana sayfa · Onay bekleyen)"] + (
            [f"- #{aid} {o['departman']}: {o['baslik']}" for o, aid in onaya] or ["- (yok)"])
        return self.iu._rapor_yaz(tarih, f"KURUL-{saat}", "\n".join(md))
