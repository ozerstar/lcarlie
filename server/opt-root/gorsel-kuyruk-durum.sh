#!/bin/bash
# Kuyrugun ve hakemin durumu tek bakista.
K=/opt/lcarlie/gorsel-kuyruk
say() { printf "  %-10s %s\n" "$1" "$(ls -1 $K/$2 2>/dev/null | wc -l)"; }
echo "KUYRUK"
say bekleyen "bekleyen/*.json"
say calisan  "calisan/*.json"
say biten    "biten/*.json"
say hata     "hata/*.json"
say cikti    "cikti/*"
echo
echo "UCLAR"
for p in 8097 8096 8095; do
  case $p in 8097) a="LLM    PC-2";; 8096) a="gomme  PC-1";; 8095) a="ComfyUI PC-2";; esac
  printf "  %-14s %s\n" "$a" "$(curl -s --max-time 5 http://127.0.0.1:$p/health 2>/dev/null || echo '-')"
done
echo
echo "SON OLAYLAR"
tail -6 $K/log/hakem.log 2>/dev/null | sed 's/^/  /' || echo "  (gunluk yok)"
