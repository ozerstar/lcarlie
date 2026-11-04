#!/usr/bin/env bash
# Anahtarlari ekrana bir kez yazar. Parola yoneticinize kaydedin.
# Bu degerler olmadan yedekleriniz ACILAMAZ ve n8n kimlik bilgileri KURTARILAMAZ.
set -euo pipefail
clear
cat <<'UYARI'
================================================================
  DIKKAT: Asagidaki degerleri SADECE parola yoneticinize kaydedin.
  Ekran goruntusu almayin, sohbete/e-postaya yapistirmayin.
  Sunucu tamamen kaybolursa yedekleri acmanin TEK yolu bunlardir.
================================================================
UYARI
echo
grep -E '^(N8N_ENCRYPTION_KEY|BACKUP_ENC_KEY|POSTGRES_PASSWORD)=' /opt/lcarlie/n8n/.env
echo
read -r -p "Kaydettiniz mi? Ekrani temizlemek icin Enter'a basin..." _
clear
echo "Ekran temizlendi."
