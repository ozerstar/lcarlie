#!/usr/bin/env python3
"""Saklama süresi dolmuş konum kayıtlarını siler.

🔴 BAKIM İŞİ DEĞİL, VERİNİN TUTULMA KOŞULU. Süresiz saklanan konum geçmişi,
toplanma amacıyla ilgisi olmayan şeyleri de anlatır: ev adresi, mesai dışı
alışkanlıklar. Zamanlayıcıya bağlanmamış bir silme politikası, yazılmış ama
uygulanmayan bir politikadır.

Ayrı dosya, çünkü systemd biriminde satır içi `python -c` yazmak tırnak
katmanlarına bağımlı ve sessizce bozulur -- 25.09.2026'da tam bu oldu.
"""
import sys

sys.path[:0] = ["/opt/lcarlie/jarvis-phase2",
                "/opt/lcarlie/jarvis-phase2/webconsole"]

from webconsole import saha  # noqa: E402


def main() -> int:
    try:
        sonuc = saha.konum_temizle()
    except Exception as exc:  # noqa: BLE001
        print("TEMIZLIK BASARISIZ: %s %s" % (type(exc).__name__, str(exc)[:200]))
        return 1
    print("silinen %d kayit · saklama %d gun"
          % (sonuc["silinen"], sonuc["saklama_gun"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
