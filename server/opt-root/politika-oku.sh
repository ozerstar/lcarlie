#!/bin/sh
# Kaynak politikasindaki tek bir anahtari okur: 'acik' | 'kapali' | 'bilinmiyor'
#
# NEDEN VAR. Panelde cevrilen anahtarlar 24.09.2026'ya kadar hicbir seyi
# degistirmiyordu: politika_oku() yalniz kendi modulu tarafindan okunuyordu.
# Bu betik, PC-2'deki hakemin o anahtari her donguda gorebilmesi icindir.
#
# 🔴 'bilinmiyor' AYRI BIR DURUMDUR. Dosya okunamadiginda 'kapali' donmek,
# bir okuma hatasini sahip karari gibi gostermek olurdu; cagiran taraf bu
# durumda MEVCUT davranisini korumali, kapatmamalidir.
ANAHTAR="$1"
DOSYA=/opt/lcarlie/jarvis-phase2/state/kaynak_politikasi.json
case "$ANAHTAR" in
  ''|*[!a-z0-9_]*) echo 'bilinmiyor'; exit 2 ;;
esac
[ -r "$DOSYA" ] || { echo 'bilinmiyor'; exit 0; }   # dosya yoksa varsayilan gecerli
python3 - "$DOSYA" "$ANAHTAR" << 'PY'
import json, sys
try:
    k = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    print('bilinmiyor'); raise SystemExit(0)
a = (k.get('anahtarlar') or {}).get(sys.argv[2])
if not isinstance(a, dict) or not isinstance(a.get('acik'), bool):
    print('bilinmiyor')
else:
    print('acik' if a['acik'] else 'kapali')
PY
