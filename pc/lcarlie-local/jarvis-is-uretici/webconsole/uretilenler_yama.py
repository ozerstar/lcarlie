"""Sunucudaki webconsole/uretilenler.py'ye ekip işleri bölümlerini ekler (idempotent, çapa kontrollü)."""
import shutil, sys, time
from pathlib import Path
p = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/lcarlie/jarvis-phase2/webconsole/uretilenler.py")
s = p.read_text(encoding="utf-8")
if "ekip_isleri" in s:
    print("zaten ekli"); sys.exit(0)
capa = "    sayi = sum(len(b.get(\"kayitlar\") or []) for b in bolumler)"
if s.count(capa) != 1:
    print("UYARI: çapa bulunamadı; uretilenler.py değişmiş. Dokunulmadı."); sys.exit(2)
shutil.copy2(p, p.with_suffix(".py.yedek-ekip-" + time.strftime("%Y%m%d%H%M%S")))
ek = ("    # İş üretici ve programların çıktıları (26.10.2026): ekip_isleri.py yalnız okur.\n"
      "    try:\n"
      "        from webconsole import ekip_isleri\n"
      "    except ImportError:\n"
      "        import ekip_isleri  # type: ignore\n"
      "    try:\n"
      "        bolumler = ekip_isleri.bolumler() + bolumler\n"
      "    except Exception as hata:  # noqa: BLE001 - bölüm okunamazsa sayfa yine açılır\n"
      "        bolumler.insert(0, {\"anahtar\": \"ekip\", \"baslik\": \"Ekip işleri\", \"durum\": \"SORAMADIM\",\n"
      "                            \"sebep\": str(hata)[:200], \"kayitlar\": []})\n")
p.write_text(s.replace(capa, ek + capa), encoding="utf-8")
print("eklendi")
