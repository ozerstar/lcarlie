#!/usr/bin/env python3
"""BasitKargo MCP kesfi — oturum kimligi ve initialized bildirimi ile.

🔴 ILK DENEME 400 ALDI. Sebep protokol: MCP HTTP tasimasinda `initialize`
cevabi bir `Mcp-Session-Id` basligi dondurur ve sonraki her istek onu
tasimak zorundadir; ayrica istemci `notifications/initialized` bildirimini
gondermeden sunucu is kabul etmez. Ikisi de eksikti.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

ENV = "/etc/lcarlie/basitkargo.env"
PROTOKOL = "2025-06-18"


def _env() -> dict[str, str]:
    d: dict[str, str] = {}
    with open(ENV, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir and "=" in satir and not satir.startswith("#"):
                k, v = satir.split("=", 1)
                d[k.strip()] = v.strip()
    return d


class Oturum:
    def __init__(self, url: str, token: str):
        self.url, self.token, self.sid = url, token, None

    def _gonder(self, govde: dict, bildirim: bool = False):
        bas = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {self.token}",
               "MCP-Protocol-Version": PROTOKOL}
        if self.sid:
            bas["Mcp-Session-Id"] = self.sid
        istek = urllib.request.Request(
            self.url, data=json.dumps(govde).encode("utf-8"), headers=bas)
        with urllib.request.urlopen(istek, timeout=90) as cevap:
            yeni = cevap.headers.get("Mcp-Session-Id")
            if yeni:
                self.sid = yeni
            ham = cevap.read().decode("utf-8", "replace")
        if bildirim or not ham.strip():
            return {}
        # SSE cevabi "id:...\nevent:message\ndata:{...}" seklinde gelir.
        # 🔴 ILK SATIR "data:" DEGIL "id:" -- bastan kontrol etmek yetmez,
        # butun satirlar taranmali. Ilk surum bu yuzden bos govde sandi.
        if "data:" in ham:
            p = [x[5:].strip() for x in ham.splitlines() if x.startswith("data:")]
            if p:
                ham = p[-1]
        return json.loads(ham)

    def cagir(self, metot: str, parametre=None, kimlik: int = 1):
        g = {"jsonrpc": "2.0", "id": kimlik, "method": metot}
        if parametre is not None:
            g["params"] = parametre
        return self._gonder(g)

    def bildir(self, metot: str):
        return self._gonder({"jsonrpc": "2.0", "method": metot}, bildirim=True)


def main() -> int:
    e = _env()
    o = Oturum(e["BASITKARGO_MCP_URL"], e["BASITKARGO_TOKEN"])
    try:
        ilk = o.cagir("initialize", {
            "protocolVersion": PROTOKOL, "capabilities": {},
            "clientInfo": {"name": "lcarlie-jarvis", "version": "1.0"}})
    except urllib.error.HTTPError as h:
        print(f"initialize HTTP {h.code}: {h.read().decode('utf-8','replace')[:300]}",
              file=sys.stderr)
        return 1
    s = (ilk.get("result") or {}).get("serverInfo") or {}
    print(f"SUNUCU: {s.get('name','?')} v{s.get('version','?')} · oturum={bool(o.sid)}")

    try:
        o.bildir("notifications/initialized")
    except Exception as hata:  # noqa: BLE001
        print(f"  (initialized bildirimi: {str(hata)[:100]})", file=sys.stderr)

    for metot, anahtar, baslik in (("tools/list", "tools", "ARAÇLAR"),
                                   ("resources/list", "resources", "KAYNAKLAR"),
                                   ("prompts/list", "prompts", "İSTEMLER")):
        try:
            c = o.cagir(metot, {}, kimlik=2)
        except urllib.error.HTTPError as h:
            print(f"\n{baslik}: HTTP {h.code} — {h.read().decode('utf-8','replace')[:200]}")
            continue
        except Exception as hata:  # noqa: BLE001
            print(f"\n{baslik}: hata {str(hata)[:150]}")
            continue
        ogeler = (c.get("result") or {}).get(anahtar) or []
        print(f"\n{baslik}: {len(ogeler)}")
        for a in ogeler:
            ad = a.get("name") or a.get("uri") or "?"
            ac = (a.get("description") or "").replace("\n", " ")[:130]
            print(f"  · {ad}")
            if ac:
                print(f"      {ac}")
            sema = a.get("inputSchema") or {}
            props = list((sema.get("properties") or {}))
            if props:
                zor = sema.get("required") or []
                print(f"      girdi: {', '.join(props[:12])}")
                if zor:
                    print(f"      zorunlu: {', '.join(zor)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

