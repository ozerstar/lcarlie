#!/usr/bin/env python3
"""MCP sunucusunun duman testi: gercek stdio istemcisiyle el sikisma + 4 cagri."""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

KOK = "/opt/lcarlie/jarvis-phase2"


async def main() -> int:
    params = StdioServerParameters(
        command=f"{KOK}/venv-mcp/bin/python",
        args=[f"{KOK}/mcp_server.py"],
        env=None,
    )
    basarisiz = 0
    async with stdio_client(params) as (okuma, yazma):
        async with ClientSession(okuma, yazma) as oturum:
            await oturum.initialize()
            print("1) EL SIKISMA: OK")

            araclar = await oturum.list_tools()
            adlar = sorted(t.name for t in araclar.tools)
            print(f"2) ARACLAR ({len(adlar)}): {', '.join(adlar)}")
            beklenen = {"sirket_sorgulari", "sirket_verisi", "gundem",
                        "kreatif_performansi"}
            if beklenen - set(adlar):
                print(f"   EKSIK: {beklenen - set(adlar)}")
                basarisiz += 1

            async def cagir(ad, arg=None):
                sonuc = await oturum.call_tool(ad, arg or {})
                return sonuc.content[0].text

            metin = await cagir("sirket_sorgulari")
            veri = json.loads(metin)
            print(f"3) sirket_sorgulari -> {veri['toplam']} izinli sorgu")
            if veri["toplam"] < 20:
                print("   BEKLENENDEN AZ"); basarisiz += 1

            metin = await cagir("gundem", {"limit": 5})
            veri = json.loads(metin)
            print(f"4) gundem -> durum={veri['durum']} "
                  f"toplam={veri.get('toplam_satir')} sure={veri.get('sure_ms')}ms")
            if veri["durum"] not in ("OK", "VERI_YOK"):
                print(f"   HATA: {veri}"); basarisiz += 1

            metin = await cagir("kreatif_performansi", {"limit": 3})
            veri = json.loads(metin)
            print(f"5) kreatif_performansi -> durum={veri['durum']} "
                  f"toplam={veri.get('toplam_satir')} donen={veri.get('donen_satir')}")
            if veri["durum"] != "OK" or not veri.get("satirlar"):
                print(f"   HATA: {str(veri)[:200]}"); basarisiz += 1
            else:
                s = veri["satirlar"][0]
                print(f"   ornek: ad_adi={s.get('ad_adi')!r} cta={s.get('cta')!r} "
                      f"ctr={s.get('ctr')}")

            # 🔴 ASIL GUVENLIK TESTI: allowlist disi ad reddedilmeli.
            metin = await cagir("sirket_verisi", {"sorgu": "DROP TABLE core.karar"})
            veri = json.loads(metin)
            print(f"6) allowlist disi ad -> durum={veri['durum']}")
            if veri["durum"] != "IZINLI_DEGIL":
                print("   🔴 REDDEDILMEDI"); basarisiz += 1

            # Izinli ad gercekten calisiyor mu (pozitif kontrol).
            metin = await cagir("sirket_verisi", {"sorgu": "urun_karti", "limit": 2})
            veri = json.loads(metin)
            print(f"7) sirket_verisi(urun_karti) -> durum={veri['durum']} "
                  f"donen={veri.get('donen_satir')}")
            if veri["durum"] != "OK":
                print(f"   HATA: {str(veri)[:200]}"); basarisiz += 1

    print("\nSONUC:", "TUM TESTLER GECTI" if basarisiz == 0 else f"{basarisiz} TEST KALDI")
    return basarisiz


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
