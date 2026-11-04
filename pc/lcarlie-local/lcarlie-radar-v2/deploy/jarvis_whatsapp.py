#!/usr/bin/env python3
"""Radar sabah özetini SAHİBE WhatsApp'tan iletir -- Jarvis'in kendi whatsapp modülüyle (beş kapı + defter).

Sahip 30.10.2026: "Telegram yerine WhatsApp kullan". Yeni bir WhatsApp kurulmadı: Jarvis'in Meta Cloud API
bağlantısı (jarvis/whatsapp.py) zaten sahibe sipariş bildirimi gönderiyor (haberci.py).

Girdi (stdin JSON): {"telefon": "...", "metin": "<tam özet>", "kisa": ["tarih", "rakip", "aday", "onay", "satis"]}
Seçenek: --kuru  -> 1-3. kapılar işler, ağa çıkılmaz (ne gidecekti?).

Yol seçimi (Meta kuralı: işletme ancak kişi son 24 saatte yazdıysa serbest metin gönderebilir;
pencere kapalıyken serbest metin istek kabul edilip sonra sessizce düşebilir):
  1. Sahip son 23 saatte işletme numarasına yazdıysa -> tam özet serbest metin (ücretsiz).
  2. Değilse -> onaylı şablon RADAR_WA_SABLON (varsayılan lcarlie_sabah_ozeti_v1), kısa özet parametreleri.
  3. Şablon yoksa/onaysızsa -> gönderilmez, sebep yazılır (özet panelde durur).
🔴 Yalnız sahibin numarasına gönderir. Üçüncü kişi (eczane vb.) bu köprüden GEÇMEZ.
Çıktı (stdout JSON): {"gonderildi": bool, "yol": "serbest|sablon|yok", "sebep": "...", ...}
"""
import json
import os
import subprocess
import sys
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))
sys.path.insert(0, str(JARVIS))

SAHIP = "".join(c for c in os.environ.get("NOBETCI_TELEFON", "905421886937") if c.isdigit())
SABLON = os.environ.get("RADAR_WA_SABLON", "lcarlie_sabah_ozeti_v1")
PENCERE_SAAT = 23   # Meta penceresi 24 saat; gönderim anı için 1 saat pay


def son_gelen_saat(telefon):
    """Sahibin işletme numarasına son yazdığı andan bu yana geçen saat (yoksa None)."""
    sql = ("SELECT EXTRACT(EPOCH FROM now() - max(m.zaman))/3600 FROM lcarlie.konusma k "
           "JOIN lcarlie.mesaj m ON m.konusma_id = k.id "
           f"WHERE k.kanal = 'whatsapp' AND k.harici_id = '{telefon}' AND m.yon = 'gelen';")
    p = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At", "-U", "n8n", "-d", "n8n"],
                       input=sql, capture_output=True, text=True, timeout=30)
    deger = (p.stdout or "").strip()
    return float(deger) if p.returncode == 0 and deger else None


def main():
    kuru = "--kuru" in sys.argv
    girdi = json.load(sys.stdin)
    telefon = "".join(c for c in str(girdi.get("telefon", "")) if c.isdigit())
    if telefon != SAHIP:
        print(json.dumps({"gonderildi": False, "yol": "yok", "sebep": "yalniz sahibin numarasina gonderilir"}))
        return 3
    from jarvis import whatsapp
    saat = son_gelen_saat(telefon)
    try:
        if saat is not None and saat < PENCERE_SAAT:
            r = whatsapp.gonder(telefon, girdi["metin"][:3900], onay_kaynagi=whatsapp.ONAY_OTOMATIK, kuru=kuru)
            yol = "serbest"
        else:
            kisa = [str(x).replace("\n", " ").replace("\t", " ")[:1000] or "-" for x in girdi["kisa"]]
            r = whatsapp.sablon_gonder(telefon, SABLON, kisa, onay_kaynagi=whatsapp.ONAY_OTOMATIK, kuru=kuru)
            yol = "sablon"
    except whatsapp.GondermeReddedildi as e:
        print(json.dumps({"gonderildi": False, "yol": "yok", "sebep": str(e), "son_gelen_saat": saat}, ensure_ascii=False))
        return 2
    print(json.dumps({"gonderildi": bool(r.get("gonderildi")), "kuru": kuru, "yol": yol,
                      "son_gelen_saat": None if saat is None else round(saat, 1), "wamid": r.get("wamid", "")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
