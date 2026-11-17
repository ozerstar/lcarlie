#!/usr/bin/env python3
"""REKLAM ÖNERİSİ — uzman ikilisi (META_MEDIA + MARKETPLACE) + kreatif önbelleği.

Sahip 15.11.2026: "yanında Jarvis ve reklam ekiplerinin önerileri, ne
yapılması gerekiyor." Saatte bir (:25, meta-reklam-izle :12'den sonra) koşar:

  1. KREATİF ÖNBELLEĞİ (her koşu): son 30 günün reklamları için 600 px küçük
     görsel + Meta önizleme bağlantısı -> state/reklam-medya/. Panel CSP'si
     dış görsele kapalı (img-src 'self'); fbcdn adresleri de imzalı ve
     süreli. Panel görseli buradan sunar. Yalnız GET.
  2. ÖNERİ (günde 2 kez 09:25 ve 18:25 + yeni KRİTİK uyarıda + --elle):
       a. webconsole/reklam_yoneticisi son 7 günü kurar (defter, başabaş,
          rozet) ve KURAL önerilerini üretir (model yokken de çalışır)
       b. her departman kendi uzman istemiyle (config/reklam-uzman) bir kez
          modele sorulur (kademe "hizli": Gemini -> OpenRouter; Claude/OpenAI
          API'si KULLANILMAZ, sahip 12.11 kararı)
       c. SAYI KAPISI: model önerisindeki 100'den büyük ya da ondalıklı her
          sayı kanıtta geçmeli; geçmiyorsa öneri düşer (sessizce değil:
          koşu kaydına yazılır)
       d. core.reklam_oneri_kosu + core.reklam_oneri yazılır; ONAY GEREKEN
          en fazla 3 öneri core.ai_sistem_onerisi ile onay kuyruğuna
          (-> WhatsApp onay hattı) düşer. Aynı öneri aynı hafta bir kez.

🔴 HİÇBİR REKLAM AYARI DEĞİŞMEZ. Meta'ya tek yazma isteği gitmez; onay
   kuyruğundaki öneri REQUEST_HUMAN_REVIEW'dur, uygulayıcısı yoktur. Sahip
   onaylasa da uygulama Ads Manager'da insan eliyledir.

Kullanım:
  reklam-oneri.py            (önbellek + vadesi geldiyse öneri)
  reklam-oneri.py --elle     (öneriyi şimdi üret)
  reklam-oneri.py --kuru     (öneriyi üret, ekrana yaz; DB'ye/kuyruğa yazma)
  reklam-oneri.py --medya    (yalnız önbellek)
  reklam-oneri.py --elle --kuyruksuz  (öneriyi yaz, onay kuyruğuna/WhatsApp'a gönderme)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

TR = timezone(timedelta(hours=3))
G = "https://graph.facebook.com/v21.0"
MEDYA = KOK / "state" / "reklam-medya"
SLOTLAR = (9, 18)              # zamanlı öneri saatleri (TR)
KUYRUK_EN_FAZLA = 3            # koşu başına onay kuyruğuna en fazla
MODEL_EN_FAZLA = 2             # departman başına modelin ek önerisi
PSQL = ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
        "-v", "ON_ERROR_STOP=1", "-tA"]


# --------------------------------------------------------------------- db
def sql(sorgu: str, degisken: dict | None = None) -> str:
    komut = list(PSQL)
    for k, v in (degisken or {}).items():
        komut += ["-v", "%s=%s" % (k, v)]
    r = subprocess.run(komut, input=sorgu, capture_output=True, text=True, timeout=90, check=False)
    if r.returncode != 0:
        raise RuntimeError("psql: " + r.stderr.strip()[:300])
    return r.stdout.strip()


def _j(veri) -> str:
    s = json.dumps(veri, ensure_ascii=False, default=str)
    if "$J$" in s:
        raise ValueError("JSON icinde $J$ var")
    return "$J$" + s + "$J$"


# --------------------------------------------------------------------- medya
def _meta(yol: str, sorgu: dict) -> dict:
    from jarvis import pazaryeri
    jeton = pazaryeri._n8n_env("META_ADS_TOKEN")
    if not jeton:
        raise RuntimeError("META_ADS_TOKEN yok")
    url = "%s/%s?%s" % (G, yol, urllib.parse.urlencode(sorgu))
    return json.loads(pazaryeri._istek(url, {"Authorization": "Bearer " + jeton}))


def medya_onbellek(tazelik_saat: int = 24) -> dict:
    """Son 30 günde görülen her reklam için 600 px görsel + önizleme bağlantısı."""
    MEDYA.mkdir(parents=True, exist_ok=True)
    os.chmod(MEDYA, 0o755)
    dizin_yolu = MEDYA / "index.json"
    try:
        dizin = json.loads(dizin_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dizin = {}
    reklamlar = [s for s in sql("SELECT DISTINCT ad_id FROM raw.meta_izleme_reklam "
                                "WHERE gun > current_date - 30;").splitlines() if s.strip()]
    simdi = datetime.now(TR)
    sayac = {"yeni": 0, "taze": 0, "hata": 0}
    for aid in reklamlar:
        kayit = dizin.get(aid) or {}
        dosya = MEDYA / ("%s.jpg" % aid)
        try:
            eski = datetime.fromisoformat(kayit.get("zaman", "2000-01-01T00:00:00+03:00"))
        except ValueError:
            eski = datetime(2000, 1, 1, tzinfo=TR)
        if dosya.exists() and simdi - eski < timedelta(hours=tazelik_saat):
            sayac["taze"] += 1
            continue
        try:
            ad = _meta(aid, {"fields": "preview_shareable_link,creative{id,video_id}"})
            kid = (ad.get("creative") or {}).get("id")
            kr = _meta(kid, {"fields": "thumbnail_url", "thumbnail_width": 600,
                             "thumbnail_height": 600}) if kid else {}
            url = kr.get("thumbnail_url")
            if url:
                with urllib.request.urlopen(url, timeout=30) as y:  # noqa: S310 - Meta CDN
                    veri = y.read(3_000_000)
                gecici = dosya.with_suffix(".tmp")
                gecici.write_bytes(veri)
                os.chmod(gecici, 0o644)
                gecici.replace(dosya)
            dizin[aid] = {"zaman": simdi.isoformat(), "onizleme": ad.get("preview_shareable_link"),
                          "video": bool((ad.get("creative") or {}).get("video_id")),
                          "gorsel": bool(url)}
            sayac["yeni"] += 1
        except Exception as h:  # noqa: BLE001 - bir reklam digerini durdurmaz
            dizin.setdefault(aid, {})["hata"] = str(h)[:160]
            sayac["hata"] += 1
    gecici = dizin_yolu.with_suffix(".tmp")
    gecici.write_text(json.dumps(dizin, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(gecici, 0o644)
    gecici.replace(dizin_yolu)
    return sayac


# --------------------------------------------------------------------- varlık (17.11)
VARLIK_EN_BUYUK_VIDEO = 200_000_000     # 200 MB
VARLIK_EN_BUYUK_GORSEL = 15_000_000


def _meta_jeton(yol: str, sorgu: dict, jeton_adi: str) -> dict:
    from jarvis import pazaryeri
    jeton = pazaryeri._n8n_env(jeton_adi)
    if not jeton:
        raise RuntimeError("%s yok" % jeton_adi)
    url = "%s/%s?%s" % (G, yol, urllib.parse.urlencode(sorgu))
    return json.loads(pazaryeri._istek(url, {"Authorization": "Bearer " + jeton}))


def _indir(url: str, hedef: Path, sinir: int) -> int:
    """Akışla indirir; sınırı aşarsa yarım dosya bırakmaz. Dönüş: bayt."""
    gecici = hedef.with_name(hedef.name + ".tmp")
    toplam = 0
    try:
        with urllib.request.urlopen(url, timeout=60) as y, open(gecici, "wb") as f:  # noqa: S310 - Meta CDN
            while True:
                parca = y.read(1 << 20)
                if not parca:
                    break
                toplam += len(parca)
                if toplam > sinir:
                    raise RuntimeError("dosya sınırı aştı (%d MB)" % (sinir // 1_000_000))
                f.write(parca)
        if toplam == 0:
            raise RuntimeError("boş dosya")
        os.chmod(gecici, 0o644)
        gecici.replace(hedef)
        return toplam
    finally:
        if gecici.exists():
            gecici.unlink()


def varlik_onbellek(yeniden_dene_saat: int = 6) -> dict:
    """raw.meta_reklam_envanter'deki her reklamın TÜM varlıkları: video (mp4 +
    kapak) ve görseller (dinamik kreatif varyasyonları, karusel kartları).
    Ad: v_<video_id>.mp4/.jpg, i_<hash>.jpg. Bir kez inen dosya değişmez
    (Meta varlığı değişmez); hata olan 6 saat sonra yeniden denenir.
    Video kaynağı yalnız sayfa jetonuyla okunuyor (17.11 ölçümü: reklam
    jetonu '#10 izin yok'). Yalnız GET."""
    MEDYA.mkdir(parents=True, exist_ok=True)
    dizin_yolu = MEDYA / "varlik.json"
    try:
        dizin = json.loads(dizin_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dizin = {}
    ham = sql("SELECT coalesce(json_agg(json_build_object('hesap', hesap_id, 'k', kreatif)), '[]') "
              "FROM raw.meta_reklam_envanter;")
    varliklar: dict[str, dict] = {}
    hesap = None
    for satir in json.loads(ham or "[]"):
        hesap = hesap or satir.get("hesap")
        for v in (satir.get("k") or {}).get("varliklar") or []:
            ad = str(v.get("ad") or "")
            if re.fullmatch(r"[vi]_k?[0-9a-fA-F]{4,64}", ad):
                varliklar.setdefault(ad, v)
    simdi = datetime.now(TR)
    sayac = {"video": 0, "gorsel": 0, "zaten": 0, "hata": 0, "bayt": 0}

    def _gec(ad):
        k = dizin.get(ad) or {}
        if not k.get("hata"):
            return False
        try:
            return simdi - datetime.fromisoformat(k["zaman"]) < timedelta(hours=yeniden_dene_saat)
        except (KeyError, ValueError):
            return False

    # Görsel hash -> adres (reklam hesabı adimages, toplu)
    hashler = [v["hash"] for a, v in varliklar.items() if v.get("hash") and not (MEDYA / (a + ".jpg")).exists()
               and not _gec(a)]
    adres: dict[str, str] = {}
    for i in range(0, len(hashler), 40):
        try:
            r = _meta_jeton("act_%s/adimages" % hesap, {"hashes": json.dumps(hashler[i:i + 40]),
                                                       "fields": "hash,url"}, "META_ADS_TOKEN")
            for g in r.get("data") or []:
                if g.get("hash") and g.get("url"):
                    adres[g["hash"]] = g["url"]
        except Exception as h:  # noqa: BLE001
            print("adimages okunamadı:", str(h)[:120], file=sys.stderr)

    for ad, v in sorted(varliklar.items()):
        try:
            if v.get("tur") == "video":
                mp4, jpg = MEDYA / (ad + ".mp4"), MEDYA / (ad + ".jpg")
                if mp4.exists() and jpg.exists():
                    sayac["zaten"] += 1
                    continue
                if _gec(ad):
                    continue
                bilgi, son = None, None
                for jeton in ("FB_PAGE_TOKEN", "META_ADS_TOKEN"):
                    try:
                        bilgi = _meta_jeton(v["video_id"], {"fields": "source,picture,length"}, jeton)
                        if bilgi.get("source"):
                            break
                    except Exception as h:  # noqa: BLE001
                        son = h
                if not (bilgi or {}).get("source"):
                    from jarvis.meta_reklam_detay import hata_sebebi
                    raise RuntimeError("video kaynağı okunamadı: %s" % (hata_sebebi(son) if son else "source alanı boş"))
                if not mp4.exists():
                    sayac["bayt"] += _indir(bilgi["source"], mp4, VARLIK_EN_BUYUK_VIDEO)
                    sayac["video"] += 1
                kapak = v.get("kapak_kaynak") or bilgi.get("picture")
                if kapak and not jpg.exists():
                    try:
                        _indir(kapak, jpg, VARLIK_EN_BUYUK_GORSEL)
                    except Exception:  # noqa: BLE001 - kapak süresi dolmuş olabilir
                        if bilgi.get("picture") and bilgi["picture"] != kapak:
                            _indir(bilgi["picture"], jpg, VARLIK_EN_BUYUK_GORSEL)
                dizin[ad] = {"zaman": simdi.isoformat(), "tur": "video", "sure": bilgi.get("length")}
            else:
                jpg = MEDYA / (ad + ".jpg")
                if jpg.exists():
                    sayac["zaten"] += 1
                    continue
                if _gec(ad):
                    continue
                url = adres.get(v.get("hash") or "") or v.get("kaynak")
                if not url:
                    raise RuntimeError("görsel adresi yok (hash çözülemedi)")
                sayac["bayt"] += _indir(url, jpg, VARLIK_EN_BUYUK_GORSEL)
                sayac["gorsel"] += 1
                dizin[ad] = {"zaman": simdi.isoformat(), "tur": "gorsel"}
        except Exception as h:  # noqa: BLE001 - bir varlık diğerini durdurmaz
            dizin[ad] = {"zaman": simdi.isoformat(), "tur": v.get("tur"), "hata": str(h)[:160]}
            sayac["hata"] += 1
    gecici = dizin_yolu.with_suffix(".tmp")
    gecici.write_text(json.dumps(dizin, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(gecici, 0o644)
    gecici.replace(dizin_yolu)
    return sayac


# --------------------------------------------------------------------- tetik
def tetik_belirle(elle: bool) -> str | None:
    if elle:
        return "ELLE"
    simdi = datetime.now(TR)
    son = sql("SELECT EXTRACT(EPOCH FROM COALESCE(max(bas_at), '2000-01-01'::timestamptz)) "
              "FROM core.reklam_oneri_kosu WHERE durum IN ('TAMAM','KISMI');")
    son_t = datetime.fromtimestamp(float(son or 0), TR)
    # yeni KRİTİK uyarı (son koşudan sonra ilk görülen)
    kritik = sql("SELECT count(*) FROM raw.meta_izleme_uyari WHERE seviye='KRITIK' "
                 "AND ilk_at > :'son'::timestamptz;", {"son": son_t.isoformat()})
    if kritik and int(kritik) > 0:
        return "KRITIK"
    for saat in SLOTLAR:
        slot = simdi.replace(hour=saat, minute=0, second=0, microsecond=0)
        if simdi >= slot and son_t < slot:
            return "ZAMANLI"
    return None


# --------------------------------------------------------------------- model
_SAYI = re.compile(r"\d[\d.,]*")


def _sayilar(metin: str) -> set[float]:
    out = set()
    for ham in _SAYI.findall(metin or ""):
        h = ham.rstrip(".,")
        aday = []
        if "," in h and "." in h:          # 1.234,56
            aday.append(h.replace(".", "").replace(",", "."))
        elif "," in h:                     # 0,49 ya da 1,234
            aday.append(h.replace(",", "."))
            aday.append(h.replace(",", ""))
        elif h.count(".") == 1 and len(h.split(".")[1]) == 3:  # 1.234 (binlik) ya da 1.234 ondalık
            aday += [h.replace(".", ""), h]
        else:
            aday.append(h.replace(".", "") if h.count(".") > 1 else h)
        for a in aday:
            try:
                out.add(float(a))
            except ValueError:
                pass
    return out


def dogrulanmayan(metin: str, kanit_sayilari: set[float]) -> list[str]:
    """100'den büyük ya da ondalıklı sayı kanıtta (±%1 / yuvarlama) geçmeli."""
    eksik = []
    for ham in _SAYI.findall(metin or ""):
        degerler = _sayilar(ham)
        if not degerler:
            continue
        if all(float(d).is_integer() and d <= 100 for d in degerler):
            continue
        tamam = False
        for d in degerler:
            for k in kanit_sayilari:
                if k == d or (k and abs(k - d) / abs(k) <= 0.01) or round(k) == d or round(k, 1) == d:
                    tamam = True
                    break
            if tamam:
                break
        if not tamam:
            eksik.append(ham.rstrip(".,"))
    return eksik


def kanit_metni(rapor: dict, dun: dict | None, bugun: dict | None) -> str:
    """Modele giden sıkı kanıt (JSON). Kişisel veri yok."""
    def reklam(s):
        d = s.get("defter") or {}
        return {"ad_id": s["ad_id"], "reklam": s["ad"], "kampanya": s["kampanya"], "set": s["set"],
                "durum": s["durum"], "hedef": s["hedef_ad"], "urun": s["urun"],
                "amac": s["amac"], "optimizasyon": s["optimizasyon"], "gunluk_butce": s["gunluk_butce"],
                "harcama": s["m"]["harcama"], "gosterim": s["m"]["gosterim"],
                "link_tiklama": s["m"]["link_tiklama"], "ctr": s["m"]["ctr"], "tbm": s["m"]["tbm"],
                "cpm": s["m"]["cpm"], "frekans": s["m"]["frekans"], "an_pay_7_gun_toplami": s["m"]["an_pay"],
                "an_harcama_son_2_gun": s.get("an_son2"), "an_son_harcama_gunu": s.get("an_son_gun"),
                "meta_satin_alma": s["m"]["satin_alma"] if s["meta_olculur"] else "OLCULEMEZ",
                "urun_defter": {k: d.get(k) for k in ("siparis", "ciro", "katki", "sonuc", "roas",
                                                       "basabas_roas", "birim_katki")} if d else None,
                "urun_reklam_sayisi": (s.get("grup") or {}).get("reklam_sayisi"),
                "rozet": s["rozet"], "rozet_neden": s["rozet_neden"], "isaretler": s["isaretler"],
                "baslik": s["kreatif"]["baslik"][:80], "metin": s["kreatif"]["govde"][:160]}
    veri = {
        "donem": rapor["aralik"], "ozet_7_gun": rapor["ozet"],
        "dun_ozet": (dun or {}).get("ozet"), "bugun_ozet": (bugun or {}).get("ozet"),
        # 17.11: aralıkta teslimi olmayan (kapalı) reklam modele gitmez;
        # yorum metni rapora hiç girmez (yalnız panelin detay ucu okur).
        "reklamlar": [reklam(s) for s in rapor["reklamlar"] if s.get("aralikta_veri", True)],
        "setler": [{"id": x["id"], "ad": x["ad"], "durum": x["durum"], "butce": x["butce"],
                    "optimizasyon": x["optimizasyon"], "harcama": x["m"]["harcama"],
                    "an_pay": x["m"]["an_pay"], "defter": x["defter"]} for x in rapor["setler"]],
        "yerlesim": rapor["yerlesim"][:12], "trend": rapor["trend"][-14:],
        "uyarilar": rapor["uyarilar"][:10], "urun_ekonomi": rapor["urun_ekonomi"],
        "kural_onerileri": [{k: o[k] for k in ("departman", "kapsam", "hedef_ad", "ne", "neden")}
                            for o in rapor["oneriler"]],
    }
    return json.dumps(veri, ensure_ascii=False, default=str)


GOREV = """Aşağıdaki <veri> L'CARLIÉ reklam hesabının ölçümüdür (son 7 gün + dün + bugün; defter = bizim siparişlerimiz, meta_* = Meta'nın iddiası; Trendyol hedefli reklamda Meta satış GÖREMEZ).
'kural_onerileri' deterministik kural motorunun önerileridir; onları TEKRARLAMA.
Kurallar: urun_defter ATIF DEĞİLDİR (ürünün o kanaldaki tüm satışıdır). En az 2 sipariş ve 1 siparişin katkısı (birim_katki) kadar harcama yoksa veri azdır: bütçe artırma önerme. Rozet KES olan ürüne bütçe artırma önerme. Audience Network tıklaması kreatif başarısı sayılmaz. Audience Network kararı YALNIZ an_harcama_son_2_gun'e bakar: 0 ise AN zaten kapalıdır, AN ile ilgili öneri YAZMA (an_pay_7_gun_toplami geçmiştir).
Görevin: senin alanında ({alan}) kural motorunun KAÇIRDIĞI en fazla {adet} somut öneri ver. Kural motoru zaten doğru söylüyorsa boş liste dön. Her sayı <veri>'de geçmeli; geçmeyen sayı yazma.
Yalnız şu JSON'u döndür, başka metin yazma:
{{"oneriler":[{{"kapsam":"HESAP|KAMPANYA|SET|REKLAM|YERLESIM|URUN","hedef_id":"<veri'deki id ya da ürün kodu>","hedef_ad":"...","oncelik":1-3,"ne":"tek cümle eylem","neden":"sayılarla, dönemle, kaynakla","beklenen_etki":"aralık + güven","risk":"...","geri_alma":"...","olcum":"ne zaman, hangi metrik","onay_gerekir":true|false,"ozet":"sahibe tek satır, sade Türkçe, rakamla"}}]}}"""


def model_onerileri(kod: str, kanit: str, kanit_sayilari: set[float],
                    an_kapali: bool = False) -> tuple[list[dict], list[str], str]:
    from jarvis import providers
    from jarvis.reklam_uzman import istem, UZMAN_ADI
    sistem = istem(kod)
    if not sistem:
        return [], ["%s: uzman istemi okunamadı" % kod], ""
    alan = {"META_MEDIA": "Meta reklam hesabı: kampanya/set/reklam/yerleşim/kreatif",
            "MARKETPLACE": "pazaryeri (Trendyol satışı, fiyat/indirim, katkı, ölçüm)"}[kod]
    mesajlar = [{"role": "system", "content": sistem},
                {"role": "user", "content": GOREV.format(alan=alan, adet=MODEL_EN_FAZLA)
                 + "\n<veri>\n" + kanit + "\n</veri>"}]
    try:
        r = providers.generate(mesajlar, max_tokens=1800, kademe="hizli", is_anahtari="reklam-oneri")
    except Exception as h:  # noqa: BLE001
        return [], ["%s: model cevap vermedi (%s)" % (kod, str(h)[:120])], ""
    metin = (r.get("text") or "").strip()
    m = re.search(r"\{.*\}", metin, re.S)
    try:
        liste = json.loads(m.group(0)).get("oneriler") or [] if m else []
    except ValueError:
        return [], ["%s: model JSON'u okunamadı" % kod], r.get("model") or ""
    out, notlar = [], []
    for o in liste[:MODEL_EN_FAZLA]:
        if not isinstance(o, dict) or not o.get("ne") or not o.get("neden"):
            continue
        tum = " ".join(str(o.get(k) or "") for k in ("ne", "neden", "beklenen_etki", "ozet"))
        # 15.11 #182: model 7 günlük AN payına bakıp kapatılmış AN için öneri yazdı.
        if an_kapali and ("audience network" in tum.lower() or " an " in (" " + tum.lower() + " ")):
            notlar.append("%s önerisi düştü (AN son 2 günde zaten kapalı): %s" % (
                UZMAN_ADI[kod], str(o.get("ne"))[:80]))
            continue
        eksik = dogrulanmayan(tum, kanit_sayilari)
        if eksik:
            notlar.append("%s önerisi düştü (doğrulanmayan sayı: %s): %s" % (
                UZMAN_ADI[kod], ", ".join(eksik[:4]), str(o.get("ne"))[:80]))
            continue
        kapsam = str(o.get("kapsam") or "HESAP").upper()
        if kapsam not in ("HESAP", "KAMPANYA", "SET", "REKLAM", "YERLESIM", "URUN"):
            kapsam = "HESAP"
        try:
            oncelik = min(3, max(1, int(o.get("oncelik") or 2)))
        except (TypeError, ValueError):
            oncelik = 2
        hid = str(o.get("hedef_id") or "hesap")[:200]
        out.append({"departman": kod, "kapsam": kapsam, "hedef_id": hid,
                    "hedef_ad": str(o.get("hedef_ad") or "")[:200], "oncelik": oncelik,
                    "ne": str(o["ne"])[:400], "neden": str(o["neden"])[:900],
                    "beklenen_etki": str(o.get("beklenen_etki") or "")[:400],
                    "risk": str(o.get("risk") or "")[:400], "geri_alma": str(o.get("geri_alma") or "")[:300],
                    "olcum": str(o.get("olcum") or "")[:300], "onay_gerekir": bool(o.get("onay_gerekir", True)),
                    "kaynak": "MODEL", "anahtar": "model:" + kod + ":" + hashlib.sha1(
                        str(o["ne"]).encode()).hexdigest()[:10],
                    "ozet": str(o.get("ozet") or o["ne"])[:240], "action_id": None})
    return out, notlar, "%s/%s" % (r.get("provider"), r.get("model"))


# --------------------------------------------------------------------- yazım
def _anahtar(o: dict, hafta: str) -> str:
    ham = "%s:%s" % (o["anahtar"], hafta)
    temiz = re.sub(r"[^A-Za-z0-9_.:-]", "-", ham)
    if len(temiz) > 110:
        temiz = temiz[:90] + "-" + hashlib.sha1(ham.encode()).hexdigest()[:12]
    return "r" + temiz


def onay_metni(o: dict) -> str:
    from jarvis.reklam_uzman import UZMAN_ADI
    # İlk satır WhatsApp onay mesajının KONUSU olur (wa-onay.py): önerinin kendisi.
    return ("Reklam: %s\n%s\nNEDEN (ölçüm): %s\nBEKLENEN ETKİ: %s\nRİSK: %s\n"
            "GERİ ALMA: %s\nÖLÇÜM PLANI: %s\n\nOnaylamak hiçbir reklam ayarını DEĞİŞTİRMEZ; "
            "uygulama Ads Manager'da elle yapılır. Jarvis paneli > KAMPANYA." % (
                o["ne"][:110], UZMAN_ADI.get(o["departman"], o["departman"]), o["neden"],
                o.get("beklenen_etki") or "—", o.get("risk") or "—", o.get("geri_alma") or "—",
                o.get("olcum") or "—"))


def kuyrukta_var(o: dict, hafta: str) -> int | None:
    """Aynı öneri bu hafta zaten kuyruğa düştüyse onun numarası (yeniden göndermez)."""
    deger = sql("SELECT action_id FROM core.ai_action_proposal WHERE idempotency_key = "
                "'action:sistem:reklam-uzman:' || :'a' ORDER BY action_id DESC LIMIT 1;",
                {"a": _anahtar(o, hafta)})
    return int(deger) if deger.strip().isdigit() else None


def kuyruga_yaz(o: dict, hafta: str) -> int | None:
    anahtar = _anahtar(o, hafta)
    metin = onay_metni(o)
    if len(metin) > 1950:
        metin = metin[:1900].rstrip() + "\n…"
    sebep = ("Reklam uzmanı önerisi (%s): %s" % (o["departman"], o["ne"]))[:480]
    deger = sql("SELECT core.ai_sistem_onerisi('reklam-uzman', 'REQUEST_HUMAN_REVIEW', :'a', "
                "jsonb_build_object('subject_ref', :'a', 'reason', :'m'), :'s');",
                {"a": anahtar, "m": metin, "s": sebep})
    return int(deger) if deger.strip().isdigit() else None


def kos(tetik: str, kuru: bool, kuyruksuz: bool = False) -> int:
    import reklam_yoneticisi as ry
    bugun = datetime.now(TR).date()
    kosu_id = None
    if not kuru:
        kosu_id = int(sql("INSERT INTO core.reklam_oneri_kosu (tetik, durum, donem_bas, donem_bit) "
                          "VALUES (:'t', 'SURUYOR', :'b', :'s') RETURNING id;",
                          {"t": tetik, "b": (bugun - timedelta(days=6)).isoformat(),
                           "s": bugun.isoformat()}).splitlines()[0])
    try:
        def kur(b, s, et):
            v = ry.veri_oku(b, s)
            v["oneri"], v["oneri_kosu"] = [], []   # kural önerileri taze üretilsin
            return ry.rapor_kur(v, b, s, etiket=et)
        r7 = kur(bugun - timedelta(days=6), bugun, "Son 7 gün")
        dun = kur(bugun - timedelta(days=1), bugun - timedelta(days=1), "Dün")
        bgn = kur(bugun, bugun, "Bugün")
        if r7.get("okunamadi"):
            raise RuntimeError("okunamayan parça: " + ", ".join(p["parca"] for p in r7["okunamadi"]))
        kural = r7["oneriler"]
        kanit = kanit_metni(r7, dun, bgn)
        sayilar = _sayilar(kanit)
        modeller, notlar, model_adi = [], [], []
        for kod in ("META_MEDIA", "MARKETPLACE"):
            m, n, ad = model_onerileri(kod, kanit, sayilar,
                                       an_kapali=r7["ozet"].get("an_son2_harcama") == 0)
            modeller += m
            notlar += n
            if ad and ad not in model_adi:
                model_adi.append(ad)
        # Kopya: aynı metin YA DA kuralın zaten hedeflediği nesne (15.11 #184 = #180).
        gorulen = {o["ne"].lower()[:60] for o in kural}
        hedefler = {h for o in kural for h in str(o.get("hedef_id") or "").split(",") if h}
        tum = kural + [o for o in modeller if o["ne"].lower()[:60] not in gorulen
                       and not (set(str(o.get("hedef_id") or "").split(",")) & hedefler)]
        tum.sort(key=lambda o: (o["oncelik"], 0 if o["kaynak"] == "KURAL" else 1))
        ozet = [o["ozet"] for o in tum[:3]]
        if not ozet:
            ozet = ["Değişiklik önerilmiyor: son 7 günde eşik ihlali yok (gün içi kurcalama öğrenmeyi bozar)."]
        if kuru:
            print(json.dumps({"tetik": tetik, "ozet": ozet, "oneriler": tum, "notlar": notlar,
                              "model": model_adi}, ensure_ascii=False, indent=1))
            return 0
        hafta = "%dw%02d" % bugun.isocalendar()[:2]
        kuyrukta = 0
        for o in tum:
            if o["onay_gerekir"] and not kuyruksuz:
                try:
                    o["action_id"] = kuyrukta_var(o, hafta)
                    if o["action_id"] is None and kuyrukta < KUYRUK_EN_FAZLA:
                        o["action_id"] = kuyruga_yaz(o, hafta)
                        kuyrukta += 1
                except RuntimeError as h:
                    notlar.append("onay kuyruğuna yazılamadı: %s" % str(h)[:120])
        satir = [{k: o.get(k) for k in ("departman", "kapsam", "hedef_id", "hedef_ad", "oncelik", "ne",
                                         "neden", "beklenen_etki", "risk", "geri_alma", "olcum",
                                         "onay_gerekir", "kaynak", "anahtar", "ozet", "action_id")}
                 for o in tum]
        sql("INSERT INTO core.reklam_oneri (kosu_id, departman, kapsam, hedef_id, hedef_ad, oncelik, ne, "
            "neden, beklenen_etki, risk, geri_alma, olcum, onay_gerekir, kaynak, anahtar, ozet, action_id) "
            "SELECT %d, departman, kapsam, hedef_id, hedef_ad, oncelik, ne, neden, beklenen_etki, risk, "
            "geri_alma, olcum, onay_gerekir, kaynak, anahtar, ozet, action_id FROM jsonb_to_recordset(%s::jsonb) "
            "AS x(departman text, kapsam text, hedef_id text, hedef_ad text, oncelik smallint, ne text, "
            "neden text, beklenen_etki text, risk text, geri_alma text, olcum text, onay_gerekir boolean, "
            "kaynak text, anahtar text, ozet text, action_id bigint);" % (kosu_id, _j(satir)))
        sql("UPDATE core.reklam_oneri_kosu SET bit_at=now(), durum=%s, model=:'m', ozet=%s::jsonb, "
            "hata=NULLIF(:'h','') WHERE id=%d;" % (
                "'KISMI'" if notlar and not modeller else "'TAMAM'", _j(ozet), kosu_id),
            {"m": ", ".join(model_adi) or "yok (yalnız kural)", "h": " | ".join(notlar)[:900]})
        print("öneri koşusu #%d: %d öneri (%d kural, %d model), %d onay kuyruğunda; %s" % (
            kosu_id, len(tum), len(kural), len(tum) - len(kural), kuyrukta, " | ".join(notlar) or "not yok"))
        return 0
    except Exception as h:
        if kosu_id:
            sql("UPDATE core.reklam_oneri_kosu SET bit_at=now(), durum='HATA', hata=:'h' WHERE id=%d;" % kosu_id,
                {"h": str(h)[:900]})
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elle", action="store_true")
    ap.add_argument("--kuru", action="store_true")
    ap.add_argument("--medya", action="store_true")
    ap.add_argument("--kuyruksuz", action="store_true")
    a = ap.parse_args()
    if not a.kuru:
        try:
            print("kreatif önbelleği:", medya_onbellek())
        except Exception as h:  # noqa: BLE001
            print("kreatif önbelleği hata:", str(h)[:160], file=sys.stderr)
        try:
            print("varlık önbelleği (video/görsel):", varlik_onbellek())
        except Exception as h:  # noqa: BLE001 - önbellek öneriyi durdurmaz
            print("kreatif önbelleği yazılamadı:", h, file=sys.stderr)
    if a.medya:
        return 0
    tetik = tetik_belirle(a.elle or a.kuru)
    if not tetik:
        print("öneri vadesi gelmedi")
        return 0
    return kos(tetik, a.kuru, a.kuyruksuz)


if __name__ == "__main__":
    sys.exit(main())
