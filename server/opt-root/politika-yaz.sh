#!/bin/sh
# Kaynak politikasindaki tek bir anahtari cevirir.
#   kullanim: politika-yaz.sh <anahtar> <acik|kapali> <kim>
#
# NEDEN VAR. PC-2'nin masaustundeki ac/kapat kisayollari bu betigi cagirir.
# Dogrudan python -c ile cagirmak, ssh -> cmd -> powershell tirnak
# katmanlarindan gecerken bozuluyordu (24.09.2026'da olculdu: anahtar
# metni bozulup curl http 000 dondu). Betik dosyasi o katmanlari yok eder.
#
# Yazma islemi sistem.politika_yaz() uzerinden yapilir, dosyaya elle
# dokunulmaz: o islev bilinmeyen anahtari reddediyor ve kim/ne zaman
# kaydini tutuyor. Burada JSON'u elle kurmak, o denetimleri atlamak olurdu.
ANAHTAR="$1"
DURUM="$2"
KIM="${3:-kisayol}"
case "$ANAHTAR" in ''|*[!a-z0-9_]*) echo 'gecersiz-anahtar'; exit 2 ;; esac
case "$DURUM" in acik) A=True ;; kapali) A=False ;; *) echo 'gecersiz-durum (acik|kapali)'; exit 2 ;; esac
case "$KIM" in *[!a-zA-Z0-9_.-]*) echo 'gecersiz-kim'; exit 2 ;; esac
cd /opt/lcarlie/jarvis-phase2 || { echo 'dizin-yok'; exit 1; }
./venv/bin/python - "$ANAHTAR" "$A" "$KIM" << 'PY'
import sys
sys.path.insert(0, '/opt/lcarlie/jarvis-phase2')
from pathlib import Path
from webconsole import sistem
anahtar, acik, kim = sys.argv[1], sys.argv[2] == 'True', sys.argv[3]
try:
    p = sistem.politika_yaz(Path('/opt/lcarlie/jarvis-phase2/state'), anahtar, acik, kim)
except ValueError as e:
    print('RET: %s' % e); raise SystemExit(2)
print('%s = %s' % (anahtar, 'acik' if p['anahtarlar'][anahtar]['acik'] else 'kapali'))
PY
