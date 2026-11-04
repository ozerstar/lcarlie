#!/bin/bash
# MOY Uyumsoft web servis bilgisini sahibin kendisi girer; şifre ekrana ve geçmişe yazılmaz.
set -euo pipefail
FILE=/etc/lcarlie/uyumsoft.env
# Windows terminalleri Enter'ı ^M (CR) olarak yolluyor: satır sonu sayılsın
stty sane icrnl 2>/dev/null || true

ask() {  # $1 = soru, $2 = "gizli" ise yazılan görünmez
    local value=""
    while [ -z "$value" ]; do
        if [ "${2:-}" = gizli ]; then read -r -s -p "$1" value; echo; else read -r -p "$1" value; fi
        value="${value//$'\r'/}"
        if [[ "$value" =~ [[:cntrl:]] ]]; then  # Ctrl+V burada yapıştırmaz, ^V karakteri yazar
            echo "  Ctrl+V bu pencerede yapıştırmaz. Sağ tıklayarak yapıştırın ya da elle yazın."
            value=""
            continue
        fi
        [ -z "$value" ] && echo "  Boş kaldı, tekrar yazın."
    done
    REPLY="$value"
}

echo "MOY - Uyumsoft web servis bilgisi (yalnız okuma için kullanılacak)"
ask "Kullanıcı adı: "; U="$REPLY"
ask "Şifre (yazarken görünmez): " gizli; P="$REPLY"
umask 077
printf 'UYUMSOFT_USER=%s\nUYUMSOFT_PASS=%s\n' "$U" "$P" > "$FILE"
chown root:root "$FILE"
chmod 600 "$FILE"
unset U P REPLY
echo "Kaydedildi. Bağlantı deneniyor..."
/opt/lcarlie/jarvis-phase2/venv/bin/python /opt/lcarlie/jarvis-phase2/tools/uyumsoft.py test
