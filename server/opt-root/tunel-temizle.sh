#!/bin/sh
# Bayat SSH ters-tunel dinleyicisini temizler.
#
# NEDEN VAR. 24.09.2026'da olculdu: ters tunelin istemci ucu yok olunca
# sunucudaki sshd oturumu portu DINLEMEYE DEVAM edebiliyor. O port artik
# cevap vermiyor ama DOLU oldugu icin yeni tunel de kurulamiyor
# ("remote port forwarding failed for listen port 8097"). PC-2 sonsuza
# kadar dener, sunucu tarafini kimse temizlemez -> kilit.
#
# KAPSAM. Yalniz verilen portu dinleyen TEK sureci oldurur. Cagiran taraf
# once portun uctan uca cevap vermedigini dogrulamis olmalidir; calisan bir
# yonlendirmeyi bu betikle yikmak, duzeltmek degil bozmaktir.
PORT="$1"
case "$PORT" in
  ''|*[!0-9]*) echo 'gecersiz-port'; exit 2 ;;
esac
PID=$(ss -tlnpH "sport = :$PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
if [ -n "$PID" ]; then
  kill "$PID" 2>/dev/null && echo "temizlendi=$PID" || echo "oldurulemedi=$PID"
else
  echo 'dinleyici-yok'
fi
