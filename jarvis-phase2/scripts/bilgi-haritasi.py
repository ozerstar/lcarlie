#!/usr/bin/env python3
"""Bilgi haritası: sohbetin her soruda her şeyi taramadan doğru cevap vermesi için.

Sahip 04.11: "her konuya hakim olsun ... ekip üyelerini, ajanları, kodları buraya bağla,
hızlı araştırsın, her şeyi taramak zorunda kalmasın ama düzgün cevap versin".

Saatte bir (lcarlie-bilgi-haritasi.timer, root) küçük, konu başlıklı markdown belgeleri
üretir; sohbetin mevcut belge araması (jarvis.company_knowledge) bunları anahtar kelimeyle
seçer ve yalnız ilgili olanı isteme koyar. Model çağrısı YOK; yalnız okur.
Çıktı: state/bilgi-haritasi/*.md (jarvis-web okuyabilir).
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

KOK = Path(os.environ.get("JARVIS_ROOT", "/opt/lcarlie/jarvis-phase2"))
CIKTI = Path(os.environ.get("BILGI_HARITASI_DIZIN", str(KOK / "state" / "bilgi-haritasi")))
KAYNAK_REPO = Path("/opt/lcarlie/source/lcarlie-jarvis-v1")
ORKESTRA = Path("/opt/lcarlie/orchestrator")
SINIR = 5500  # bir belge; sohbet bütçesine 2-3 belge sığsın

sys.path.insert(0, str(KOK))


def belge(ad: str, konu: str, anahtar: list[str], govde: str) -> tuple[str, str]:
    if len(govde) > SINIR:
        govde = govde[:SINIR].rsplit("\n", 1)[0] + "\n…(kısaltıldı)"
    bas = (f"---\nkonu: {konu}\nanahtar: [{', '.join(sorted(set(anahtar)))}]\n"
           f"gizlilik: ic-bilgi\n---\n\n")
    return ad, bas + f"# {konu}\n\n_Otomatik bilgi haritası · {dt.datetime.now():%d.%m.%Y %H:%M}_\n\n" + govde


def ekipler() -> list[tuple[str, str]]:
    from jarvis import roster
    uyeler = roster.departman_uyeleri()
    sorumlu = getattr(roster, "DEPARTMAN_SORUMLUSU", {})
    satir, parcalar = [], []
    for kod in sorted(uyeler):
        u = uyeler[kod]
        satir.append(f"## {kod} (sorumlu: {sorumlu.get(kod, '-')})")
        for m in u:
            satir.append(f"- **{m.name}** ({m.key}): {m.job}")
        satir.append("")
    metin = "\n".join(satir)
    # Bütçeye sığması için departman gruplarına böl.
    blok, cikti = [], []
    for parca in metin.split("\n## "):
        parca = parca if parca.startswith("## ") else "## " + parca
        if sum(len(b) for b in blok) + len(parca) > SINIR - 400 and blok:
            cikti.append(blok)
            blok = []
        blok.append(parca)
    if blok:
        cikti.append(blok)
    for i, b in enumerate(cikti, 1):
        kodlar = [w for x in b if x.startswith("## ") for w in x.split()[1].lower().split("_")]
        parcalar.append(belge(f"50-ekipler-{i}", f"ekipler, departmanlar ve üyeler ({i}/{len(cikti)})",
                              ["ekip", "ekipler", "departman", "departmanlar", "üye", "üyeler", "kim",
                               "sorumlu", "müdür", "ajan", "ajanlar", "kadro", *kodlar],
                              "\n".join(b)))
    return parcalar


def programlar() -> tuple[str, str]:
    r = subprocess.run(["systemctl", "list-timers", "--all", "--no-pager", "--no-legend", "lcarlie-*"],
                       capture_output=True, text=True, timeout=20, check=False)
    satir = []
    for line in r.stdout.splitlines():
        p = line.split()
        tim = next((x for x in p if x.endswith(".timer")), None)
        if not tim:
            continue
        acik = subprocess.run(["systemctl", "show", tim, "-p", "Description", "--value"],
                              capture_output=True, text=True, timeout=5, check=False).stdout.strip()
        sonraki = " ".join(p[1:3]) if len(p) > 3 and p[0] not in ("n/a", "-") else "-"
        satir.append(f"- `{tim}` — {acik} · sonraki: {sonraki}")
    return belge("51-sistem-programlar", "otomatik programlar, zamanlayıcılar ve nöbetler",
                 ["program", "programlar", "zamanlayıcı", "timer", "nöbet", "otomatik", "saat kaçta",
                  "ne zaman çalışıyor", "sistem", "çalışan işler", "cron"],
                 f"{len(satir)} zamanlayıcı:\n\n" + "\n".join(satir))


def _ilk_satir(yol: Path) -> str:
    try:
        d = ast.get_docstring(ast.parse(yol.read_text(encoding="utf-8")))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return ""
    return (d or "").strip().splitlines()[0][:140] if d else ""


def kod_haritasi() -> list[tuple[str, str]]:
    out = []
    for etiket, dizin, desen in (("jarvis çekirdek modülleri", KOK / "jarvis", "*.py"),
                                 ("panel (webconsole) modülleri", KOK / "webconsole", "*.py"),
                                 ("betikler (scripts)", KOK / "scripts", "*.py")):
        satir = []
        for p in sorted(dizin.glob(desen)):
            if ".yedek" in p.name or p.name.startswith("test_"):
                continue
            satir.append(f"- `{p.relative_to(KOK)}` — {_ilk_satir(p) or '(açıklama yok)'}")
        ad = "52-kod-" + dizin.name
        out.append(belge(ad, f"kod haritası: {etiket}",
                         ["kod", "kodlar", "modül", "dosya", "nerede", "hangi dosya", "repo", "depo",
                          "kaynak kod", "fonksiyon", dizin.name], "\n".join(satir)))
    if ORKESTRA.is_dir():
        dosyalar = sorted(x.name for x in ORKESTRA.iterdir()
                          if x.is_file() and ".yedek" not in x.name and not x.name.startswith(".env"))
        out.append(belge("52-kod-orchestrator", "orchestrator (n8n yanı, eylem işçisi) dosyaları",
                         ["orchestrator", "orkestra", "orkestrasyon", "action worker", "eylem işçisi",
                          "onay", "n8n", "kod", "repo"],
                         "Konum: /opt/lcarlie/orchestrator\n\n" + "\n".join(f"- `{x}`" for x in dosyalar)))
    if (KAYNAK_REPO / ".git").exists():
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(KAYNAK_REPO), "log",
                            "--oneline", "-25"], capture_output=True, text=True, timeout=10, check=False)
        out.append(belge("52-kod-son-degisiklikler", "son kod değişiklikleri (git geçmişi)",
                         ["değişiklik", "commit", "son değişiklikler", "ne değişti", "git", "güncelleme",
                          "kod", "repo"],
                         f"Depo: {KAYNAK_REPO} (dal tarayici-worker)\n\n```\n{r.stdout.strip()}\n```"))
    return out


def ekip_durumu() -> list[tuple[str, str]]:
    iu = KOK / "state" / "is-uretici"
    out = []
    ozetler = sorted(iu.glob("ozet-*.md"))
    if ozetler:
        out.append(belge("53-ekip-gunluk-ozet", "ekiplerin bugünkü işleri ve teslimleri (iş üretici özeti)",
                         ["ekipler bugün", "bugün ne", "bugünkü", "ekipler ne yaptı", "ne yaptı", "yaptılar", "ekiplerin", "teslim", "teslimler", "iş", "işler", "görev",
                          "görevler", "rapor", "ekip durumu", "çalışıyor mu", "özet"],
                         ozetler[-1].read_text(encoding="utf-8")))
    kurullar = sorted((iu / "raporlar").glob("*/KURUL-*.md"))
    if kurullar:
        out.append(belge("53-karar-kurulu", "karar kurulunun son kararları (red team, ana karar)",
                         ["kurul", "karar", "kararlar", "red team", "onay", "öneri", "ana karar", "exec"],
                         kurullar[-1].read_text(encoding="utf-8")))
    try:
        agac = json.loads((iu / "agac.json").read_text(encoding="utf-8"))
        satir = []
        for kod, d in sorted((agac.get("departmanlar") or {}).items()):
            acik = [g for g in d.get("gorevler", []) if g.get("durum") == "ACIK"]
            if acik:
                satir.append(f"- **{kod}** ({len(acik)} açık): " + "; ".join(
                    str(g.get("baslik"))[:70] for g in acik[:3]))
        out.append(belge("53-acik-isler", "ekiplerin açık işleri (departman başına ilk 3)",
                         ["açık iş", "açık işler", "bekleyen iş", "sırada", "yapılacak", "görev", "ekip"],
                         "\n".join(satir)))
    except (OSError, ValueError):
        pass
    return out


def main() -> int:
    belgeler: list[tuple[str, str]] = []
    for uret in (ekipler, lambda: [programlar()], kod_haritasi, ekip_durumu):
        try:
            belgeler += uret()
        except Exception as e:  # noqa: BLE001 - bir bölüm düşerse diğerleri yazılsın
            print(f"uyarı: {getattr(uret, '__name__', 'bolum')}: {e}", file=sys.stderr)
    CIKTI.mkdir(parents=True, exist_ok=True)
    yazilan = set()
    for ad, metin in belgeler:
        yol = CIKTI / f"{ad}.md"
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(metin, encoding="utf-8")
        gecici.replace(yol)
        os.chmod(yol, 0o644)
        yazilan.add(yol.name)
    for eski in CIKTI.glob("*.md"):
        if eski.name not in yazilan:
            eski.unlink()
    print(json.dumps({"belge": len(yazilan), "dizin": str(CIKTI)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
