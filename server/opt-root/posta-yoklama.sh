#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - ALARM POSTASI CANLILIK YOKLAMASI
#
# NEDEN VAR
# saglik.sh'nin ALARMPOSTA kontrolu "son basarili gonderim" ile "son
# basarisiz gonderim" zamanlarini karsilastirir. Mantik dogru ama KOR
# NOKTASI var: "posta yine calisiyor" bilgisini yalnizca GERCEK bir alarm
# gonderildiginde ogrenebiliyor. Sistem saglikli kaldigi surece yeni
# gonderim olmaz, son olay basarisizlik olarak kalir ve panel sonsuza
# kadar "Alarm e-postasi gonderilemiyor" der.
#
# 21-22.09.2026'da tam bu oldu: 17:48 ve 18:49'da Yandex yavasladi, iki
# gonderim 25 sn'de zaman asimina ugradi. Ertesi sabah SMTP 2 saniyede
# 250 OK veriyordu ama panel hala FAILED gosteriyordu - olcebilecegi yeni
# bir olay yoktu.
#
# 🔴 BU BETIK POSTA GONDERMEZ. Baglanir, TLS kurar, kimlik dogrular ve
#    QUIT der. Sahibin gelen kutusuna hicbir sey dusmez - cunku cozmeye
#    calistigimiz sikayet zaten "bir suru hata maili geldi" idi. Test
#    maili atan bir canlilik kontrolu, hastaligin kendisi olurdu.
#
# 🔴 PAROLA HICBIR KOSULDA YAZDIRILMAZ. .msmtprc yalnizca okunur; hata
#    metinleri sabit dizgelere indirgenir, sunucu cevabi oldugu gibi
#    basilmaz (SMTP cevaplari kimlik bilgisi tasiyabilir).
#
# Kullanim:
#   ./posta-yoklama.sh          Gerekliyse yoklar (saatte en fazla bir kez)
#   ./posta-yoklama.sh --zorla  Kisitlamayi yok say, hemen yokla
# =============================================================================
set -uo pipefail

KOK="${LCARLIE_KOK:-/opt/lcarlie}"
MSMTPRC="${MSMTPRC:-/root/.msmtprc}"
YOKLAMA_LOG="$KOK/alarm-yoklama.log"
ARALIK_DK="${POSTA_YOKLAMA_ARALIK_DK:-60}"
ZAMAN_ASIMI="${POSTA_YOKLAMA_ZAMAN_ASIMI:-20}"

ZORLA=0
[ "${1:-}" = "--zorla" ] && ZORLA=1

yaz() {
  printf '%s|%s|%s\n' "$(date -Is)" "$1" "$2" >>"$YOKLAMA_LOG" 2>/dev/null || true
  printf '%s %s\n' "$1" "$2"
}

# --- Kisitlama: Yandex'i saatte 96 kez kimlik dogrulamaya zorlamayalim -------
# saglik.sh 15 dakikada bir calisiyor. Her calistirmada giris yapmak, once
# postayi yavaslatan seyin ta kendisi olurdu.
if [ "$ZORLA" = "0" ] && [ -f "$YOKLAMA_LOG" ]; then
  SON_EPOCH="$(date -d "$(tail -n1 "$YOKLAMA_LOG" 2>/dev/null | cut -d'|' -f1)" +%s 2>/dev/null || echo 0)"
  SIMDI="$(date +%s)"
  if [ "$SON_EPOCH" -gt 0 ] 2>/dev/null; then
    GECEN_DK=$(( (SIMDI - SON_EPOCH) / 60 ))
    if [ "$GECEN_DK" -lt "$ARALIK_DK" ]; then
      exit 0   # sessizce cik: son yoklama hala taze
    fi
  fi
fi

[ -r "$MSMTPRC" ] || { yaz "HATA" "yapilandirma okunamadi"; exit 1; }
command -v python3 >/dev/null 2>&1 || { yaz "HATA" "python3 yok"; exit 1; }

# 🔴 Parola python'a ARGUMAN olarak gecmez: argumanlar `ps` ciktisinda
#    sunucudaki her kullaniciya gorunur. Dosya yolu verilir, degeri
#    python kendisi okur.
SONUC="$(MSMTPRC="$MSMTPRC" ZA="$ZAMAN_ASIMI" python3 - <<'PY' 2>/dev/null
import os, smtplib, ssl, sys

ayar = {}
try:
    with open(os.environ["MSMTPRC"], "r", encoding="utf-8", errors="replace") as f:
        for satir in f:
            parca = satir.split(None, 1)
            if len(parca) == 2:
                ayar.setdefault(parca[0].strip(), parca[1].strip())
except OSError:
    print("HATA|yapilandirma okunamadi"); sys.exit(0)

host = ayar.get("host"); kul = ayar.get("user"); par = ayar.get("password")
try:
    port = int(ayar.get("port", "465"))
except ValueError:
    port = 465
starttls = ayar.get("tls_starttls", "off").lower() == "on"
za = float(os.environ.get("ZA", "20"))

if not (host and kul and par):
    print("HATA|yapilandirma eksik"); sys.exit(0)

try:
    if starttls:
        s = smtplib.SMTP(host, port, timeout=za)
        s.starttls(context=ssl.create_default_context())
    else:
        s = smtplib.SMTP_SSL(host, port, timeout=za,
                             context=ssl.create_default_context())
    try:
        s.login(kul, par)
        # 🔴 Burada DURULUR. sendmail cagrilmaz, DATA gonderilmez.
        print("OK|baglanti+kimlik dogrulandi")
    finally:
        try: s.quit()
        except Exception: pass
# 🔴 Istisna metni BASILMAZ: SMTP cevaplari kimlik bilgisi tasiyabilir.
#    Her sinif sabit bir dizgeye indirgenir.
except smtplib.SMTPAuthenticationError:
    print("HATA|kimlik dogrulanamadi (parola degismis olabilir)")
except (TimeoutError, OSError):
    print("HATA|baglanilamadi veya zaman asimi")
except ssl.SSLError:
    print("HATA|TLS kurulamadi")
except smtplib.SMTPException:
    print("HATA|SMTP protokol hatasi")
PY
)"

[ -n "$SONUC" ] || SONUC="HATA|yoklama calismadi"
yaz "${SONUC%%|*}" "${SONUC#*|}"
[ "${SONUC%%|*}" = "OK" ] || exit 1
exit 0
