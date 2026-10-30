# -*- coding: utf-8 -*-
"""Instagram paketinden ÇEKİM FÖYÜ üretir.

Sahip: "tüm reelsler elde çekiliyor ama bunların indirilebilir veya
promptlanabilir halde olması lazım. bazı reelsler Higgsfield veya benzeri
portallarda yapay zekâ ile üretiliyor, burdaki işlemler için açıkça
detayların belirtilmesi gerekir."

Paketin kendisi NE söyleneceğini söylüyor; föy NASIL çekileceğini söyler.
Saniye saniye plan, ekrandaki yazı, mevzuat sınırı ve -- AI portalına
gidilecekse -- oraya yapıştırılacak istem.

🔴 AI PORTALINDA METİNDEN VİDEO ÜRETİLMEZ, GÖRSELDEN ÜRETİLİR.
Metinden üreten mod ambalajı UYDURUR: kapak, pompa, etiket, oran hepsi
AI'nın icadı olur ve o kare L'CARLIÉ ürünü değildir. Portalda başlangıç
karesi olarak ELİMİZDEKİ gerçek dosya yüklenir, istem yalnız HAREKETİ
tarif eder. Bu, "AI kullanma" yasağı değil; AI'ya ürünü çizdirmeme
kuralıdır.

🔴 MEVZUAT SINIRI ELLE YAZILMAZ. Yasak ifade listesi jarvis.compliance'tan
okunur; orada bir kural değişince föy de değişir. Elle yazılsaydı föy,
kuralın altı ay önceki hâlini ezberlemiş olurdu.
"""
from __future__ import annotations
import json

# Reels iskeleti: toplam 18 sn. Kısaltılabilir, ama SIRA değişmez --
# ilk 2 saniyede ürün görünmezse izleyici kaydırır (ölçülmüş sebep
# paketin kendi dayanağında yazılı).
REELS_PLANI = [
    ("00:00-00:02", "AÇILIŞ",
     "Ürün ELDE. Tek hareket: kutudan/raftan alınıp kadraja giriyor. "
     "Yazı YOK -- ilk iki saniye ürünün."),
    ("00:02-00:06", "KANCA",
     "Ürün sabit, kadraj hafif yaklaşıyor. Ekranda kanca yazısı belirir."),
    ("00:06-00:12", "KULLANIM",
     "Gerçek uygulama: elin üstüne/cilde sürülüyor. Yakın plan, doku "
     "görünsün. Oyunculuk yok, gerçek hareket."),
    ("00:12-00:16", "İÇERİK",
     "Makro: dokunun yayılışı ya da ambalaj detayı (kapak, etiket). "
     "Ekranda içerik cümlesi."),
    ("00:16-00:18", "KAPANIŞ",
     "Ürün tam kadrajda, sabit. Ekranda marka ve çağrı."),
]

TEK_GORSEL_PLANI = [
    ("kare", "TEK KARE",
     "Ürün fotoğrafı hazır (1080x1080). Çekim gerekmiyor; yazı tasarım "
     "katmanında dizili geliyor."),
]

# Portalda istemin BAŞLIĞI degil, KURULUMU önemli: yanlış modda
# çalıştırmak ambalajı uydurur.
PORTAL_KURULUMU = [
    ("mod", "image-to-video (görselden video). "
            "text-to-video KULLANILMAZ -- ambalajı uydurur."),
    ("başlangıç karesi", "%s (bu paketin kendi dosyası, panelden indirilir)"),
    ("en-boy", "9:16 dikey"),
    ("çözünürlük", "1080x1920"),
    ("süre", "5 sn üretip döngüye alın; portal 15 sn veriyorsa tek seferde"),
    ("kamera", "çok yavaş push-in ya da sabit. Hızlı kamera hareketi "
               "ambalaj kenarlarını bozar."),
]

NEGATIF_ISTEM = (
    "distorted packaging, warped label, changed bottle shape, extra text, "
    "misspelled text, invented logo, different cap, morphing product, "
    "hands with extra fingers, watermark, beauty filter on product, "
    "flowers, pebbles, leaves, beige gradient background"
)


def _mevzuat_satirlari() -> list:
    """Yasak ifade başlıkları -- compliance modülünden, elle değil."""
    from jarvis import compliance as c

    return [
        ("üstünlük iddiası", ", ".join(c.SUPERIORITY[:4]) + " ..."),
        ("içermez/arındırılmış", ", ".join(c.ICERMEZ[:3]) + " ..."),
        ("dosya isteyen iddia", ", ".join(c.DOSSIER_REQUIRED[:3]) + " ..."),
        ("otorite ödünçleme", ", ".join(c.AUTHORITY[:3]) + " ..."),
        ("öncesi/sonrası", ", ".join(c.BEFORE_AFTER[:3]) + " ..."),
        ("kalite işareti", ", ".join(c.QUALITY_MARKS) + " (ürün üstünde değil)"),
    ]


def _cizgi(baslik: str) -> str:
    return "\n" + baslik + "\n" + "-" * len(baslik) + "\n"


def foy_metni(paket: dict, urun: dict | None = None) -> str:
    """Paketten çekim föyü. Panelden .txt olarak inen metin."""
    if not isinstance(paket, dict) or not paket.get("plan_id"):
        raise ValueError("paket bos")

    bicim = paket.get("bicim") or "REELS"
    urun = urun or {}
    cumleler = [s.strip() for s in (paket.get("caption") or "").split("\n")
                if s.strip()]
    kanca = paket.get("kanca") or (cumleler[0] if cumleler else "")
    govde = [s for s in cumleler if s != kanca]

    p = []
    p.append("L'CARLIÉ · ÇEKİM FÖYÜ")
    p.append("=" * 58)
    p.append("paket %s · %s · %s · %s"
             % (paket.get("plan_id"), (urun.get("ad") or paket.get("urun_slug")),
                paket.get("amac"), bicim))
    if bicim == "REELS":
        p.append("15-25 sn · dikey 1080x1920 · altyazı ZORUNLU")
        p.append("(izleyicinin büyük kısmı sessiz izler; altyazısız video "
                 "izlenmiş sayılmaz)")
    elif bicim == "STORY":
        p.append("hikâye · dikey 1080x1920 · kare başına 5-7 sn")
    elif bicim == "KARUSEL":
        p.append("karusel · 1080x1350 · ilk kare kancadır")
    else:
        p.append("tek kare · 1080x1080")

    p.append(_cizgi("1. NE ANLATIYOR"))
    p.append("kanca: " + kanca)
    for s in govde:
        p.append("       " + s)
    p.append("")
    p.append("çağrı (CTA): %s" % (paket.get("cta") or "—"))
    if paket.get("cta_gerekce"):
        p.append("gerekçe: " + paket["cta_gerekce"])
    if paket.get("dayanak"):
        p.append("")
        p.append("neden bu ürün: " + paket["dayanak"])

    # Gunluk paket (30.10.2026) kendi senaryosunu/karelerini tasir; varsa
    # genel plan yerine O basilir. Genel plan yalniz haftalik paket icindir.
    sen = paket.get("senaryo") or {}
    if isinstance(sen, str):
        try:
            sen = json.loads(sen)
        except ValueError:
            sen = {}
    satirlar = sen.get("senaryo") or []
    kareler = sen.get("kareler") or []
    p.append(_cizgi("2. PLAN PLAN ÇEKİM"))
    if paket.get("ekran_kancasi"):
        p.append("ekran kancası (ilk kare): " + paket["ekran_kancasi"])
        p.append("")
    if satirlar:
        for s in satirlar:
            p.append("%-8s görüntü: %s" % (s.get("sn", ""), s.get("goruntu", "")))
            if s.get("ses"):
                p.append("%-8s ses    : %s" % ("", s["ses"]))
            if s.get("ekran"):
                p.append("%-8s ekran  : %s" % ("", s["ekran"]))
    elif kareler:
        for k in kareler:
            p.append("KARE %s · %s" % (k.get("no", ""), k.get("baslik", "")))
            if k.get("metin"):
                p.append("         " + k["metin"])
            if k.get("etkilesim") and k["etkilesim"] != "yok":
                p.append("         etkileşim: " + k["etkilesim"])
    else:
        plan = REELS_PLANI if bicim == "REELS" else TEK_GORSEL_PLANI
        for an, ad, tarif in plan:
            p.append("%-12s %-10s %s" % (an, ad, tarif))
    if paket.get("uzman_notu"):
        p.append("")
        p.append("İNSTAGRAM İÇERİK DİREKTÖRÜ: " + paket["uzman_notu"])

    p.append(_cizgi("3. EKRANDAKİ YAZI"))
    p.append("🔴 Yazı TASARIM KATMANINDA dizilir. AI'ya yazı yazdırılmaz --")
    p.append("   harfleri bozar ve marka yazı tipini taklit eder.")
    p.append("   Başlık: Monument Extended · Gövde: Metropolis")
    p.append("")
    p.append("🔴 AŞAĞIDAKİ CÜMLELER EKRAN İÇİN UZUN. Ekranda 6 saniyede")
    p.append("   okunabilecek kadar kısalt -- ama kısaltılmış cümle,")
    p.append("   mevzuat denetiminden GEÇMEMİŞ YENİ bir cümledir.")
    p.append("   Kısalttıktan sonra panelden denetlet.")
    p.append("")
    p.append("00:02  " + kanca)
    for i, s in enumerate(govde[:2]):
        p.append("%s  %s" % (("00:06" if i == 0 else "00:12"), s))
    p.append("00:16  L'CARLIÉ · %s" % (paket.get("cta") or ""))
    if paket.get("hashtagler"):
        p.append("")
        p.append("açıklamaya: " + " ".join(paket["hashtagler"]))

    p.append(_cizgi("4. BU VİDEODA SÖYLENEMEZ / YAZILAMAZ"))
    p.append("Kural: denetlenen şey fiil değil, cümlenin NESNESİDİR.")
    p.append("\"Cildin görünümüne yardımcı olur\" serbest;")
    p.append("\"egzamayı geçirir\" değil -- nesne hastalık olduğu an iddiadır.")
    p.append("")
    for ad, ornek in _mevzuat_satirlari():
        p.append("  · %-22s %s" % (ad, ornek))
    zorunlu = urun.get("zorunlu_uyarilar") or []
    if zorunlu:
        p.append("")
        p.append("BU ÜRÜNDE ZORUNLU İBARE (videoda ya da açıklamada geçmeli):")
        for z in zorunlu:
            p.append("  · " + str(z))

    p.append(_cizgi("5. YAPAY ZEKÂ PORTALI (Higgsfield vb.) İÇİN"))
    p.append("🔴 Bu bölüm YALNIZ portalda üretilecekse kullanılır.")
    p.append("   Elde çekim yapılıyorsa 2. bölüm yeterlidir.")
    p.append("")
    dosya = paket.get("gorsel_dosya") or "(bu pakette görsel yok)"
    for ad, deger in PORTAL_KURULUMU:
        p.append("  %-18s %s" % (ad, (deger % dosya) if "%s" in deger else deger))
    p.append("")
    p.append("HAREKET İSTEMİ (portala yapıştır):")
    p.append("")
    p.append("  " + _hareket_istemi(paket, urun))
    p.append("")
    p.append("NEGATİF İSTEM (portala yapıştır):")
    p.append("")
    p.append("  " + NEGATIF_ISTEM)
    p.append("")
    p.append("🔴 Çıkan videoyu kabul etmeden önce ambalaja BAK: kapak, pompa,")
    p.append("   etiket yazısı, şişe oranı, renk. Biri değiştiyse kare")
    p.append("   L'CARLIÉ ürünü değildir, atılır.")

    p.append(_cizgi("6. TESLİM"))
    p.append("dosya adı : lcarlie-%s-%s.mp4" % (paket.get("urun_slug"),
                                                paket.get("plan_id")))
    p.append("nereye    : panele yükle, paketi YAYINLANDI işaretle")
    p.append("")
    p.append("Bu föy panelden üretildi; paket değişirse föy de değişir.")
    return "\n".join(p) + "\n"


def _hareket_istemi(paket: dict, urun: dict) -> str:
    """Portala yapıştırılacak İngilizce hareket istemi.

    Ürünü TARİF ETMEZ -- başlangıç karesi zaten gerçek ürün. Tarif
    etseydik portal onu yeniden çizmeye çalışırdı.
    """
    return (
        "Animate the provided still image. Keep the product exactly as it "
        "is: do not redraw, reshape, relabel or retexture the packaging. "
        "Very slow push-in, subtle natural hand movement, soft daylight "
        "from the left, gentle shadow shift. Calm, editorial, unhurried. "
        "No added objects, no added text, no background change."
    )
