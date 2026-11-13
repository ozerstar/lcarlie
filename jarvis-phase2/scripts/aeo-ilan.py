"""Ankara Eczacı Odası İlan Panosu -> ilan metinleri + içlerindeki telefon/e-posta (JSONL)."""
import html
import json
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36",
      "X-Requested-With": "XMLHttpRequest"}
EPOSTA = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
TEL = re.compile(r"(?<!\d)(?:\+?90[\s.-]?)?\(?0?\s?([2-5]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{2})[\s.-]?(\d{2})(?!\d)")


def al(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def metin(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", h, flags=re.S)
    return re.sub(r"\s*\n\s*", "\n", html.unescape(re.sub(r"<[^>]+>", "\n", h))).strip()


def main(cikti, en_fazla_sayfa=400):
    linkler, sayfa = [], 1
    while sayfa <= en_fazla_sayfa:
        try:
            d = json.loads(al(f"https://www.aeo.org.tr/page/ilanlar?page={sayfa}"))
        except Exception as e:  # noqa: BLE001
            print("sayfa", sayfa, "HATA", e)
            break
        yeni = re.findall(r'href="(https://www\.aeo\.org\.tr/[^"]+)"[^>]*title="([^"]*)"', d.get("html", ""))
        tarih = re.findall(r"<strong>(\d\d\.\d\d\.\d{4})", d.get("html", ""))
        if not yeni:
            break
        for i, (u, b) in enumerate(yeni):
            linkler.append((u, html.unescape(b), tarih[i] if i < len(tarih) else ""))
        sayfa += 1
        time.sleep(0.7)
    linkler = list(dict.fromkeys(linkler))
    print(len(linkler), "ilan,", sayfa - 1, "sayfa; en eski", linkler[-1][2] if linkler else "-", flush=True)
    with open(cikti, "w", encoding="utf-8") as f:
        for n, (u, baslik, tarih) in enumerate(linkler, 1):
            try:
                t = metin(al(u))
            except Exception as e:  # noqa: BLE001
                print(u, "HATA", e)
                continue
            # Başlık önce <title>'da geçer; ilan gövdesi "Anasayfa" kırıntısından sonra başlar
            a = t.find("Anasayfa\n")
            govde = t[a + 9:a + 2600] if a >= 0 else t[:2500]
            govde = govde.replace("İlan Panosu\n", "", 1)
            govde = govde.split("AEO Mobil Uygulamalar")[0]
            teller = sorted({"".join(m) for m in TEL.findall(govde)} - {"3124250708", "3124254296"})
            epostalar = sorted({e.lower() for e in EPOSTA.findall(govde)} - {"aeo@aeo.org.tr"})
            f.write(json.dumps({"url": u, "baslik": baslik, "tarih": tarih, "teller": teller,
                                "epostalar": epostalar, "metin": govde[:1500]}, ensure_ascii=False) + "\n")
            if n % 50 == 0:
                print(n, "ilan okundu", flush=True)
            time.sleep(0.7)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400)
