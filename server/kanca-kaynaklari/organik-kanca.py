#!/usr/bin/env python3
"""ORGANİK kanca: tutan kısa videolardan konuşulan açılış cümlesi.

NEDEN BU KAYNAK
===============
🔴 Havuzdaki her şey ÜCRETLİ reklamdan geliyordu. "SESLI" kancalar bile Ad
Library videolarından, yani hepsi sponsorlu. Sahip iki kez "hem doğal tutan
videolar" dedi ve o yarı gerçekten boştu.

🔴 NEDEN YOUTUBE, NEDEN TIKTOK/INSTAGRAM DEĞİL. TikTok ve Instagram çekimi
çerez istiyor ve kırılgan. YouTube yt-dlp ile çerezsiz ARANABİLİYOR ve --
asıl önemlisi -- **İZLENME SAYISI veriyor**. Ad Library ticari reklamda
harcamayı gizlediği için orada tek vekilimiz "kaç gündür yayında"ydı;
burada doğrudan ölçülmüş bir tutma sinyali var.

Ölçüldü (21.09.2026, "saç bakım spreyi"):
    1.383.081 izlenme ·  13 sn · Dalin Peri Işıltısı Kolay Tarama Spreyi
       78.333 izlenme ·  47 sn · Elidor Ekspres Bakım Spreyi
          189 izlenme ·  85 sn · ŞipŞak Taranmayan Boyalı Saçlar
Aradaki fark dört basamak: eşik koymadan "piyasa böyle yapıyor" demek,
kimsenin izlemediği videoyu örnek almak olur.

GİRDİ  (stdin, JSON): {"kategoriler": [...], "azami": 6, "asgari_izlenme": 20000}
ÇIKTI  (stdout, JSON): [{"metin","kanal","izlenme","sure","video_id","baslik"}]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# 🔴 WHISPER KONUŞMA YOKKEN UYDURUR. Ölçüldü: müzikli, konuşmasız bir
# reklamda transkript "Altyazı M.K" çıktı -- modelin eğitim verisindeki
# altyazı jeneriklerinden gelen bir sanrı. Bu havuza kanca diye girseydi,
# senaryo üreticisine "piyasada kullanılan açılış cümlesi" olarak giderdi.
# Sessizlik bir veri değil, veri YOKLUĞUDUR; uydurma ile doldurulmaz.
UYDURMA = (
    "altyazı", "altyazi", "abone ol", "amara.org", "subtitle",
    "kanalıma abone", "beni izlediğiniz", "teşekkürler izlediğiniz",
    "m.k.", "mk.", "bu videoyu", "iyi seyirler",
)


def uydurma_mi(metin: str) -> bool:
    duz = metin.casefold().strip()
    if len(duz.split()) < 3:          # iki kelimelik "kanca" yoktur
        return True
    return any(k in duz for k in UYDURMA)


SANIYE = 8            # kanca ilk saniyelerde
AZAMI_SURE = 120      # kısa form; uzun vlog kancası bize uymaz
ARAMA_BASINA = 8
MODEL_ADI = "small"

YTDLP = Path(__file__).resolve().parent / "venv-kanca" / "bin" / "yt-dlp"


# 🔴 TEK SORGU YETMIYOR. Ölçüldü: "saç bakım spreyi" tek başına arandığında
# eşiği geçen (kısa + çok izlenen) video sayısı 2'ye kadar düşüyordu ve
# YouTube araması koşudan koşuya farklı sonuç veriyor -- bir koşuda Dalin'i,
# diğerinde OGX'i getirdi. Aynı kategoriyi birkaç farklı ifadeyle aramak
# hem aday havuzunu büyütüyor hem koşular arası dalgalanmayı azaltıyor.
#
# "shorts" eki kısa formu doğrudan hedefliyor; "nasıl kullanılır" ve "rutin"
# ise UGC/anlatım videolarını getiriyor -- bizim aradığımız kanca türü orada.
SORGU_EKLERI = ("", " shorts", " nasıl kullanılır", " rutin")


def ara(kategori: str) -> list[dict]:
    """Kategori için YouTube araması; yalnız üstveri, indirme yok."""
    bulunan: list[dict] = []
    for ek in SORGU_EKLERI:
        bulunan.extend(_tek_arama(f"{kategori}{ek}"))
    return bulunan


def _tek_arama(sorgu: str) -> list[dict]:
    komut = [str(YTDLP), f"ytsearch{ARAMA_BASINA}:{sorgu}",
             "--dump-json", "--no-warnings", "--skip-download"]
    try:
        r = subprocess.run(komut, capture_output=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError):
        return []
    bulunan = []
    for satir in r.stdout.decode("utf-8", "replace").splitlines():
        try:
            d = json.loads(satir)
        except json.JSONDecodeError:
            continue
        bulunan.append({
            "video_id": d.get("id"),
            "baslik": str(d.get("title") or "")[:120],
            "kanal": str(d.get("uploader") or "")[:60],
            "izlenme": d.get("view_count") or 0,
            "sure": d.get("duration") or 0,
            "url": d.get("webpage_url") or f"https://www.youtube.com/watch?v={d.get('id')}",
        })
    return bulunan


def _indir(komut: list[str], hedef: Path) -> bool:
    try:
        r = subprocess.run(komut, capture_output=True, timeout=240)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0 and hedef.exists() and hedef.stat().st_size > 1000


def ses_al(url: str, hedef: Path) -> bool:
    """İlk saniyeleri indirir; olmazsa TAM sesi indirir.

    🔴 KESİTLİ İNDİRME HER VİDEODA ÇALIŞMIYOR. Ölçüldü: dört adayın birinde
    `--download-sections` başarısız oldu ve o video sessizce elendi -- üstelik
    elenen, aramadaki EN ÇOK İZLENEN videoydu. En değerli örneği kaybetmek,
    hiç örnek almamaktan kötü.

    Yedek yol güvenli çünkü aday havuzu zaten <=120 sn'lik kısa videolarla
    sınırlı: tam ses indirmek birkaç yüz KB.
    """
    taban = str(hedef.with_suffix(""))
    kesitli = [str(YTDLP), url, "-f", "bestaudio/best",
               "--download-sections", f"*0-{SANIYE}",
               "--force-keyframes-at-cuts", "-x", "--audio-format", "wav",
               "-o", taban, "--no-warnings", "--quiet"]
    if _indir(kesitli, hedef):
        return True
    tam = [str(YTDLP), url, "-f", "bestaudio/best", "-x",
           "--audio-format", "wav", "-o", taban, "--no-warnings", "--quiet"]
    return _indir(tam, hedef)


def main() -> int:
    try:
        istek = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[]")
        return 1
    kategoriler = [k for k in (istek.get("kategoriler") or []) if k]
    azami = int(istek.get("azami") or 6)
    asgari = int(istek.get("asgari_izlenme") or 20000)
    if not kategoriler:
        print("[]")
        return 0

    adaylar: dict[str, dict] = {}
    for kategori in kategoriler[:3]:
        for v in ara(kategori):
            # 🔴 İKİ ELEME. Kısa form olmayan (vlog) kancası bizim formatımıza
            # uymaz; az izlenen video "tutan içerik" değildir.
            if not v["video_id"] or v["sure"] > AZAMI_SURE:
                continue
            if v["izlenme"] < asgari:
                continue
            adaylar.setdefault(v["video_id"], v)

    secilen = sorted(adaylar.values(), key=lambda v: v["izlenme"], reverse=True)[:azami]
    if not secilen:
        print("[]", file=sys.stdout)
        print("organik: esigi gecen kisa video bulunamadi", file=sys.stderr)
        return 0

    from faster_whisper import WhisperModel

    model = WhisperModel(MODEL_ADI, device="cpu", compute_type="int8")
    cikti = []
    with tempfile.TemporaryDirectory() as gecici:
        for v in secilen:
            ses = Path(gecici) / f"{v['video_id']}.wav"
            if not ses_al(v["url"], ses):
                print(f"organik: ses alinamadi {v['video_id']}", file=sys.stderr)
                continue
            try:
                parcalar, _ = model.transcribe(str(ses), language="tr", beam_size=1)
                metin = " ".join(p.text.strip() for p in parcalar).strip()
            except Exception:  # noqa: BLE001
                continue
            ilk = metin.split(". ")[0].strip(" .")
            if 10 <= len(ilk) <= 200 and not uydurma_mi(ilk):
                cikti.append({
                    "metin": ilk, "kanal": v["kanal"], "izlenme": v["izlenme"],
                    "sure": v["sure"], "video_id": v["video_id"],
                    "baslik": v["baslik"],
                })
            ses.unlink(missing_ok=True)

    print(json.dumps(cikti, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
