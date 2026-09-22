"""BasitKargo MCP istemcisi — okuma serbest, PARA HARCAYAN adım onaya bağlı.

Sahip 21.09.2026 kimliği verdi ve şunu istedi: *"buradan hazırladığım
gönderi bilgileri ile otomatik kargo barkodu oluşturabilmek, taşıyıcıyı
seçebilmek, karşı ödemeli mi biz mi ödemeli gibi bilgileri seçebilme."*

UÇTA NE VAR — ölçüldü (46 araç, `scripts/kargo-kesif.py`):
  ÜCRETSİZ   create_shipment · update_shipment · get_shipment_fee ·
             list_shipments · search_shipments · track_shipment ·
             get_label · delete_order · cancel_shipment
  🔴 PARALI  generate_shipment_code · bulk_generate_codes · create_return
             ("THIS CHARGES THE FIRM'S BALANCE and calls the carrier")

🔴 PARALI ARAÇLAR BU MODÜLDEN DOĞRUDAN ÇAĞRILMAZ.
`PARALI` kümesindeki bir araç `cagir()` ile istenirse modül REDDEDER.
Sebep: bunlar dış dünyada geri alınamaz iş yapar ve şirketin bakiyesinden
para düşer. Sistemin tamamı "öneri üret, insan onaylasın" üzerine kurulu;
kargo kodu üretmek de o kapıdan geçer. Onaylanmış bir öneriyi yürütmek
için `onayli=True` açıkça verilir ve bunu yalnız onay hattı yapar.

🔴 TASLAK ÜCRETSİZDİR, O YÜZDEN SERBEST. `create_shipment` kargo
çağırmaz, para düşmez, sadece kayıt açar. Onu da onaya bağlamak paneli
kullanılamaz kılardı: sahip önce taslağı kurar, fiyatları görür, sonra
hangi taşıyıcıya para vereceğine karar verir.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

ENV_YOLU = os.environ.get("BASITKARGO_ENV", "/etc/lcarlie/basitkargo.env")
PROTOKOL = "2025-06-18"

# 🔴 Bu kümedeki her araç ŞİRKETİN BAKİYESİNDEN PARA DÜŞÜRÜR.
# Uçtaki açıklamalardan birebir alındı, tahmin edilmedi.
PARALI = frozenset({
    "generate_shipment_code",   # "THIS CHARGES THE FIRM'S BALANCE"
    "bulk_generate_codes",      # "CHARGES the firm for every successful order"
    "create_return",            # "Charges a return shipment fee"
})

# Dış dünyaya yazan ama para düşürmeyenler: yine de dikkatli davranılır,
# panelde onay sorulur ama modül seviyesinde engellenmez.
YAZAN = frozenset({
    "create_shipment", "update_shipment", "cancel_shipment", "delete_order",
    "print_label", "create_automation", "set_automation_enabled",
    "create_ticket", "reply_ticket",
})


class KargoHatasi(RuntimeError):
    """Uç hata döndürdü ya da çağrı reddedildi."""


def _kimlik() -> tuple[str, str]:
    d: dict[str, str] = {}
    try:
        with open(ENV_YOLU, encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if satir and "=" in satir and not satir.startswith("#"):
                    k, v = satir.split("=", 1)
                    d[k.strip()] = v.strip()
    except OSError as hata:
        raise KargoHatasi(f"kimlik dosyası okunamadı: {hata}") from hata
    url, tok = d.get("BASITKARGO_MCP_URL", ""), d.get("BASITKARGO_TOKEN", "")
    if not url or not tok:
        raise KargoHatasi("BASITKARGO_MCP_URL / BASITKARGO_TOKEN eksik")
    return url, tok


class Kargo:
    """Tek oturumluk MCP istemcisi.

    🔴 OTURUM ZORUNLU. Uç, `initialize` cevabında `Mcp-Session-Id` döndürür
    ve sonraki her isteğin onu taşımasını ister; ayrıca
    `notifications/initialized` gönderilmeden iş kabul etmez. İkisi de
    eksikken uç HTTP 400 döndü (ölçüldü).
    """

    def __init__(self, url: str | None = None, token: str | None = None,
                 zaman_asimi: int = 90):
        if url is None or token is None:
            url, token = _kimlik()
        self.url, self.token, self.zaman_asimi = url, token, zaman_asimi
        self.sid: str | None = None
        self._sayac = 0
        self._hazir = False

    # -- taşıma -----------------------------------------------------------
    def _gonder(self, govde: dict, bildirim: bool = False) -> dict:
        basliklar = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "MCP-Protocol-Version": PROTOKOL,
        }
        if self.sid:
            basliklar["Mcp-Session-Id"] = self.sid
        istek = urllib.request.Request(
            self.url, data=json.dumps(govde).encode("utf-8"), headers=basliklar)
        try:
            with urllib.request.urlopen(istek, timeout=self.zaman_asimi) as cevap:
                yeni = cevap.headers.get("Mcp-Session-Id")
                if yeni:
                    self.sid = yeni
                ham = cevap.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as hata:
            govde_h = hata.read().decode("utf-8", "replace")[:300]
            raise KargoHatasi(f"HTTP {hata.code}: {govde_h}") from hata
        except Exception as hata:  # noqa: BLE001
            raise KargoHatasi(f"bağlanılamadı: {str(hata)[:200]}") from hata

        if bildirim or not ham.strip():
            return {}
        # 🔴 SSE cevabı "id:…\nevent:message\ndata:{…}" ile gelir; İLK SATIR
        # "data:" DEĞİLDİR. Baştan kontrol eden ilk sürüm gövdeyi boş sandı.
        if "data:" in ham:
            parcalar = [s[5:].strip() for s in ham.splitlines()
                        if s.startswith("data:")]
            if parcalar:
                ham = parcalar[-1]
        try:
            return json.loads(ham)
        except ValueError as hata:
            raise KargoHatasi(f"cevap çözülemedi: {ham[:200]}") from hata

    def _rpc(self, metot: str, parametre: Any = None) -> dict:
        self._sayac += 1
        g: dict[str, Any] = {"jsonrpc": "2.0", "id": self._sayac, "method": metot}
        if parametre is not None:
            g["params"] = parametre
        cevap = self._gonder(g)
        if "error" in cevap:
            h = cevap["error"]
            raise KargoHatasi(f"{h.get('code')}: {str(h.get('message'))[:200]}")
        return cevap.get("result") or {}

    def baglan(self) -> dict:
        if self._hazir:
            return {}
        sonuc = self._rpc("initialize", {
            "protocolVersion": PROTOKOL, "capabilities": {},
            "clientInfo": {"name": "lcarlie-jarvis", "version": "1.0"}})
        self._gonder({"jsonrpc": "2.0", "method": "notifications/initialized"},
                     bildirim=True)
        self._hazir = True
        return sonuc

    # -- araçlar ----------------------------------------------------------
    def araclar(self) -> list[dict]:
        self.baglan()
        return self._rpc("tools/list", {}).get("tools") or []

    def cagir(self, arac: str, girdi: dict | None = None, *,
              onayli: bool = False) -> dict:
        """Aracı çağırır.

        🔴 PARALI araç `onayli=True` olmadan ÇAĞRILMAZ. Bu bayrağı yalnız
        onay hattı verir; panel ya da bir betik kendiliğinden veremez.
        """
        if arac in PARALI and not onayli:
            raise KargoHatasi(
                f"'{arac}' şirketin bakiyesinden PARA DÜŞÜRÜR ve taşıyıcıyı "
                "çağırır. Onay hattından geçmeden çalıştırılamaz.")
        self.baglan()
        sonuc = self._rpc("tools/call", {"name": arac,
                                         "arguments": girdi or {}})
        return _icerik_coz(sonuc)


def _icerik_coz(sonuc: dict) -> dict:
    """MCP `content` dizisini kullanılabilir bir sözlüğe indirger.

    Uç metin döndürüyorsa JSON olarak çözmeyi dener; olmuyorsa metni
    OLDUĞU GİBİ taşır -- uydurma bir yapı üretmez.
    """
    icerik = sonuc.get("content")
    if not isinstance(icerik, list):
        return sonuc
    metinler, gorseller = [], []
    for p in icerik:
        tur = p.get("type")
        if tur == "text" and p.get("text"):
            metinler.append(p["text"])
        elif tur == "image" and p.get("data"):
            gorseller.append({"mime": p.get("mimeType"), "veri": p["data"]})
    cikti: dict[str, Any] = {}
    if gorseller:
        cikti["gorseller"] = gorseller
    if metinler:
        birlesik = "\n".join(metinler)
        try:
            cozulen = json.loads(birlesik)
            cikti["veri"] = cozulen
        except ValueError:
            cikti["metin"] = birlesik
    if sonuc.get("isError"):
        cikti["hata"] = True
    return cikti or sonuc

