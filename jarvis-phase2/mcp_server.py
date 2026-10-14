#!/usr/bin/env python3
"""Company Memory'yi MCP aracı olarak açar. SALT OKUNUR.

NEDEN VAR
Şirket verisine ulaşmanın tek yolu ya web konsolu ya da elle
`ssh lcarlie` + `docker exec psql` yazmaktı. Bir dış istemciden (Claude
Code gibi) aynı veriye ulaşmak için her seferinde kabuk komutu kurmak
gerekiyordu; kabuk komutu kurmak da SQL'i elle yazmak demek, yani
allowlist'in DIŞINA çıkmak demek. Bu sunucu o yolu kapatır: dışarıdan
gelen istek **yalnızca** CompanyMemory'nin izin verdiği sorguları
çalıştırabilir.

GÜVENLİK YÜZEYİ GENİŞLEMEDİ -- üç katman aynen duruyor:
  1. `CompanyMemory._fetch` allowlist'te olmayan adı ValueError ile reddeder.
  2. Kullanıcı metni SQL'e HİÇ girmez; sorgu adı yalnızca sabit bir sözlükte
     anahtar olarak aranır.
  3. Her sorgu `SET SESSION AUTHORIZATION ai_reader` altında ve `ROLLBACK`
     ile biten bir işlemde koşar -- yazma yapısal olarak imkânsız.

V1 BİLEREK SALT OKUNUR
Hatırlatma eklemek (`core.acik_soru`'ya INSERT) ayrı bir rol ve ayrı bir
karar ister. `EXTERNAL_ACTIONS=false` duruşuyla tutarlı olsun diye bu
sürüme konmadı; yazma açılacaksa ayrı bir CR olarak açılır.

"SORAMADIM" İLE "VERİ YOK" AYRI ŞEYLERDİR
Bu projede ölçülmüş bir tuzak: boş sonuç "yok" diye okunursa yanlış karar
verilir. Sorgu çalıştı ve 0 satır döndüyse `durum: VERI_YOK`; sorgu hiç
çalışamadıysa `durum: SORAMADIM` + sebep. İkisi asla karıştırılmaz.

ÇALIŞTIRMA
    venv-mcp/bin/python mcp_server.py        # stdio, istemci başlatır
İstemci tarafı yapılandırması README_MCP.md içinde.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from jarvis.memory import CompanyMemory, MemoryError  # noqa: E402

# Sunucu bu makinede çalışır; CompanyMemory'nin varsayılanı olan "lcarlie"
# SSH takma adı sunucunun KENDİSİNDE çözülmez (ölçülmüş tuzak). Bu yüzden
# yerel docker yolu varsayılandır; uzaktan çalıştırmak isteyen açıkça
# JARVIS_SSH_HOST verir.
_HOST = os.environ.get("JARVIS_SSH_HOST") or None
_memory = CompanyMemory(host=_HOST)

# Tek cevabın taşıyabileceği karakter tavanı. Aşılırsa satır atılır ve
# atıldığı SÖYLENİR -- sessizce kırpmak, eksik veriyi tam veri gibi
# göstermek olurdu.
_TAVAN = 12000

# Sorgu adı -> ne içerdiği. Model bunu okuyup hangisini isteyeceğine karar
# verir, o yüzden açıklamalar Türkçe ve somut.
_ACIKLAMA: dict[str, str] = {
    "agenda": "Şirket gündemi: açık sorular, önceliğe göre (P0->P4)",
    "open_work": "Açık işler: cevapsız mesaj, bekleyen karar, süresi geçen iş",
    "kreatif_performans": "Reklam KREATİFİ düzeyi: başlık, gövde, CTA, biçim + CTR/CPM/frekans",
    "advertising_performance": "Reklam (ad_id) düzeyi: harcama, gösterim, tıklama, 7/14/30 gün",
    "advertising_spend": "Kampanya düzeyi günlük harcama (ad_id YOK -- kreatif analizinde kullanma)",
    "urun_karti": "Ürün kartı: fiyat, stok, maliyet, marj, platform farkı",
    "urun_bilgi": "Ürünün TAM metni -- içindekiler listesi dahil (kırpılmamış)",
    "ecommerce_price": "Fiyat gerçeği: müşteriye söylenecek fiyat ve kaynağı",
    "ecommerce_profitability": "Ürün kârlılığı: ciro, maliyet, brüt marj",
    "sales_orders": "Siparişler",
    "sales_items": "Sipariş kalemleri",
    "crm_customers": "Müşteri kimlikleri ve sipariş geçmişi",
    "crm_unanswered": "CEVAPSIZ müşteri konuşmaları ve ne kadardır beklediği",
    "operations_shipments": "Kargo/gönderi durumu",
    "gunluk_brief": "Günlük yönetici özeti",
    "data_quality": "Veri kalitesi kapıları -- rakama güvenilir mi",
    "decision_summary": "Karar özeti",
    "learning_loop": "Geçmiş kararların sonucu",
    "system": "Orkestratör sağlığı",
    "capabilities": "Model politikası / yetenek durumu",
}


def _paket(sorgu: str, records: list[dict[str, Any]], latency_ms: float,
           limit: int) -> str:
    """Satırları istemciye JSON olarak verir; kırpmayı açıkça bildirir."""
    toplam = len(records)
    if limit > 0:
        records = records[:limit]
    govde = {
        "sorgu": sorgu,
        "kaynak": f"postgres:{sorgu}",
        "otorite": "CANONICAL_COMPANY_MEMORY",
        "durum": "VERI_YOK" if toplam == 0 else "OK",
        "toplam_satir": toplam,
        "donen_satir": len(records),
        "sure_ms": latency_ms,
        "satirlar": records,
    }
    metin = json.dumps(govde, ensure_ascii=False, indent=1)
    while len(metin) > _TAVAN and records:
        # Tavanı aşarsak sondan at, kaç tane attığımızı say.
        records = records[:-1]
        govde["satirlar"] = records
        govde["donen_satir"] = len(records)
        govde["kirpildi"] = (
            f"{toplam} satirin {len(records)}'i donduruldu -- cevap boyut "
            f"tavanini asti. Daha dar bir sorgu sec veya limit kullan."
        )
        metin = json.dumps(govde, ensure_ascii=False, indent=1)
    return metin


def _calistir(sorgu: str, limit: int) -> str:
    try:
        kanit = _memory._fetch(sorgu)
    except ValueError:
        izinli = ", ".join(sorted(_memory.QUERIES))
        return json.dumps({
            "sorgu": sorgu, "durum": "IZINLI_DEGIL",
            "aciklama": "Bu sorgu adi allowlist'te yok. Serbest SQL calistirilamaz.",
            "izinli_sorgular": izinli,
        }, ensure_ascii=False, indent=1)
    except MemoryError as hata:
        # 🔴 Burasi "veri yok" DEGIL. Sorgu hic calisamadi.
        return json.dumps({
            "sorgu": sorgu, "durum": "SORAMADIM",
            "sebep": str(hata)[:400],
            "aciklama": "Sorgu calistirilamadi. Bu, 'veri yok' ile AYNI SEY DEGILDIR -- "
                        "sonuc bilinmiyor, sifir degil.",
        }, ensure_ascii=False, indent=1)
    except Exception as hata:  # noqa: BLE001
        return json.dumps({
            "sorgu": sorgu, "durum": "SORAMADIM",
            "sebep": f"{type(hata).__name__}: {str(hata)[:300]}",
        }, ensure_ascii=False, indent=1)
    return _paket(sorgu, kanit.records, kanit.latency_ms, limit)


mcp = MCPServer(
    name="lcarlie-company-memory",
    instructions=(
        "L'CARLIE sirket verisine SALT OKUNUR erisim. Serbest SQL yok: yalniz "
        "allowlist'teki sorgu adlari calisir. Bir rakam verirken hangi sorgudan "
        "geldigini soyle. 'durum' alani VERI_YOK ise gercekten sifir satir vardir; "
        "SORAMADIM ise sonuc BILINMIYOR -- bu ikisini asla karistirma."
    ),
)


@mcp.tool()
def sirket_sorgulari() -> str:
    """Hangi sirket sorgularinin calistirilabilecegini listeler.

    Once bunu cagir. Serbest SQL calistirilamaz; yalniz burada donen adlar
    `sirket_verisi` aracina verilebilir.
    """
    satirlar = []
    for ad in sorted(_memory.QUERIES):
        satirlar.append({"sorgu": ad, "icerik": _ACIKLAMA.get(ad, "(aciklama yok)")})
    return json.dumps({
        "toplam": len(satirlar),
        "not": "Serbest SQL yok. Yalniz bu adlar calisir.",
        "sorgular": satirlar,
    }, ensure_ascii=False, indent=1)


@mcp.tool()
def sirket_verisi(sorgu: str, limit: int = 25) -> str:
    """Allowlist'teki bir sirket sorgusunu calistirir ve satirlari dondurur.

    Args:
        sorgu: `sirket_sorgulari` ciktisindaki adlardan biri. Baska bir sey
            verilirse calistirilmaz, izinli adlar geri dondurulur.
        limit: Donen en fazla satir sayisi (0 = sinirsiz, boyut tavanina kadar).
    """
    return _calistir(sorgu, limit)


@mcp.tool()
def gundem(limit: int = 25) -> str:
    """Sirket gundemi: acik sorular ve bekleyen isler, onceligiyle.

    "Ne yapmam lazim", "bekleyen is ne var", "gundem ne" sorularinin cevabi.
    """
    return _calistir("agenda", limit)


@mcp.tool()
def kreatif_performansi(limit: int = 30) -> str:
    """Reklam KREATIFI performansi: hangi baslik/CTA/bicim ne getirdi.

    🔴 CTR satis DEGILDIR ve farkli CTA'lar dogrudan kiyaslanamaz (profil
    goruntuleme tiklamasi ucuzdur ama satis degildir). Kapsama 1/3 reklam
    hesabi -- 3 hesabin 2'sinde erisim izni yok.
    """
    return _calistir("kreatif_performans", limit)


if __name__ == "__main__":
    mcp.run("stdio")
