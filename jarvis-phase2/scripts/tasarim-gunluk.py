"""TASARIM DEPARTMANI GÜNLÜK NÖBETİ — "biz demeden yapan ekip".

Sahip 22.09.2026: *"hatta biz demeden yapan ekip olsun."*

🔴 "BIZ DEMEDEN YAPMAK" URETIM DEGIL, GORME DEMEK. Kimse istemeden
tasarim uretip sahibin onune yigmak, onay kuyrugunu cope cevirir ve
para harcar. Departmanin kendiliginden yaptigi is sudur: HER GUN
kutuge ve deftere bakip TIKANIKLIGI bulmak ve adiyla soylemek.

Uc soru soruyor, ucune de veriden cevap veriyor:
  1. Hangi is turu tanimli ama URETILEMIYOR? (sablonu yok)
  2. Onay kuyrugunda bekleyen var mi, kac gundur?
  3. Hangi urunun kesilmis gorseli YOK? (sablon dolduramaz)

🔴 RAPOR UYDURMAZ. Hicbir madde model cagrisiyla uretilmiyor; hepsi
sayimdir. Soylenecek bir sey yoksa "bugun tikanan yok" der -- paneli
doldurmak icin cumle kurmaz.

🔴 ONERI YAZAR, IS YAPMAZ. Cikti `core.tasarim_isi` degil; bu bir
uretim degil. Rapor state/ altina yaziliyor ve panel okuyor. Uretim
kararini sahip verir.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")

RAPOR = Path("/opt/lcarlie/jarvis-phase2/state/tasarim-nobet.json")


def oku(sql: str) -> list[dict]:
    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
         "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=40, check=False)
    if r.returncode:
        raise RuntimeError((r.stderr or "")[:300])
    out = []
    for satir in (r.stdout or "").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                pass
    return out


def main():
    bulgular = []

    # 1 ── şablonu olmayan iş türleri
    tikali = oku(
        "SELECT row_to_json(t) FROM (SELECT kategori, count(*) AS adet, "
        "string_agg(ad, '; ' ORDER BY sablon_kodu) AS isler "
        "FROM mart.tasarim_sablon_kutuk WHERE NOT uretilebilir AND aktif "
        "GROUP BY kategori ORDER BY count(*) DESC) t;")
    for t in tikali:
        bulgular.append({
            "tur": "SABLON_EKSIK", "kategori": t["kategori"],
            "adet": t["adet"],
            "mesaj": (f"{t['kategori'].upper()}: {t['adet']} iş türü tanımlı "
                      "ama üretilemiyor — Canva tasarımı bağlanmamış."),
            "ornek": (t["isler"] or "")[:180]})

    # 2 ── onay kuyruğu
    bekleyen = oku(
        "SELECT row_to_json(t) FROM (SELECT count(*) AS adet, "
        "min(uretildi) AS en_eski FROM mart.tasarim_guncel "
        "WHERE onay_bekliyor) t;")
    if bekleyen and bekleyen[0]["adet"]:
        b = bekleyen[0]
        bulgular.append({
            "tur": "ONAY_BEKLIYOR", "adet": b["adet"],
            "mesaj": (f"{b['adet']} tasarım onay bekliyor. En eskisi: "
                      f"{str(b['en_eski'])[:16]}."),
        })

    # 3 ── görseli olmayan ürünler
    kunye = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun/cekim-kesim/tanima.json")
    if kunye.exists():
        try:
            tanima = json.loads(kunye.read_text(encoding="utf-8"))
            bilinen = {t.get("urun") for t in tanima
                       if t.get("urun") and t["urun"] != "BELIRSIZ"}
            kutu = Path("/opt/lcarlie/jarvis-phase2/varliklar/kutu-gercegi")
            tum = {p.stem.upper() for p in kutu.glob("*.json")
                   if not p.stem.startswith("_")}
            eksik = sorted(tum - bilinen)
            if eksik:
                bulgular.append({
                    "tur": "GORSEL_EKSIK", "adet": len(eksik),
                    "mesaj": (f"{len(eksik)} ürünün kesilmiş görseli yok — "
                              "şablonun görsel alanı doldurulamaz."),
                    "ornek": ", ".join(eksik[:12])})
        except Exception as e:  # noqa: BLE001
            bulgular.append({"tur": "HATA",
                             "mesaj": f"ürün görsel künyesi okunamadı: {e}"})

    rapor = {
        "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bulgu_sayisi": len(bulgular),
        "bulgular": bulgular,
        # 🔴 Söylenecek bir şey yoksa cümle KURMAZ.
        "ozet": (bulgular[0]["mesaj"] if bulgular
                 else "Bugün tıkanan iş yok."),
    }
    RAPOR.write_text(json.dumps(rapor, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    print(f"[{rapor['zaman']}] {len(bulgular)} bulgu -> {RAPOR}")
    for b in bulgular:
        print("  •", b["mesaj"])


if __name__ == "__main__":
    main()
