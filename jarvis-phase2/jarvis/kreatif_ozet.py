"""Kreatif partisinin onay kuyruğunda görünecek özeti.

Ayrı modül çünkü İKİ yerden çağrılıyor: `scripts/kreatif-inceleme.py`
(inceleme biter bitmez ekrana basmak için) ve `jarvis/loop.py` (öneriyi
sahibin kuyruğuna yazarken). Tireli betikten import edilemeyeceği için
buraya alındı; iki kopya tutmak, ikisinin ayrışması demekti.

🔴 Bağımlılığı yok ve olmayacak. `jarvis/loop.py` bilerek dar bir import
kümesi taşıyor (business_signals, action_contract, coding_executor,
firewall, memory); buraya ağır bir şey konursa döngü onu da yüklenir.
"""
from __future__ import annotations

from typing import Any

# core.ai_propose_action 'reason' alanını 2000 baytta reddediyor
# (coding_executor.py:65 aynı sınırı MAX_REASON_CHARS ile taşıyor).
# 1900 payı, çok baytlı Türkçe harfler için bırakılmıştır: "ö" iki bayt,
# karakter saymak bayt saymak DEĞİLDİR.
AZAMI_GEREKCE = 1900

ISARET = {"GECER": "+", "DUZELT": "~", "RED": "x"}


def brief_ozeti(brief: dict[str, Any], parti: str,
                taban_url: str = "/kreatif") -> str:
    """Birinci onay: brief ve promptlar hazır, GÖRSEL ÜRETİMİ için izin.

    🔴 Bu öneri onaylanmadan tek bir görsel üretilmez. O yüzden burada
    sahibin "üretmeye değer mi" sorusuna cevap verecek şeyler var:
    ürün hangi fiyatta nerede duruyor, rakip ne yapıyor, kaç cümle
    denetimden düştü, kaç prompt hazır. Görselin kendisi HENÜZ YOK.
    """
    urun = (brief.get("urun") or {}).get("urun_adi") or "?"
    fk = brief.get("fiyat_konumu_olcumu") or {}
    gorseller = brief.get("gorseller") or []
    silinen = brief.get("mevzuat_silinen") or []
    kurul = brief.get("kurul") or []
    rakip = brief.get("rakip") or []
    tutarsiz = brief.get("tutarlilik") or []

    # 🔴 İLK SATIR SORU. Kuyruğa bakan kişinin gözü önce EYLEMİ görmeli;
    # ölçüm ve gerekçe altta. Bir önceki biçim başlıkla açılıyordu ve
    # "neyin onayı bu?" sorusuna yol açtı.
    s = [f"{urun} için {len(gorseller)} reklam görseli üretilsin mi?",
         "",
         f"parti  : {parti}",
         "durum  : promptlar hazır · GÖRSEL HENÜZ ÜRETİLMEDİ"]
    if fk.get("cumle"):
        s.append(f"fiyat  : {fk['cumle']}")
    s.append(f"rakip  : {len(rakip)} açıdan tarandı "
             f"({', '.join(str(r.get('aci')) for r in rakip)})")
    s.append(f"ekip   : {len(kurul)} departman veriden konuştu")
    s.append(f"denetim: {len(silinen)} cümle silindi (mevzuat/dayanaksız iddia)")
    if tutarsiz:
        s.append(f"🔴 UYARI: kendi eski reklamlarımızın {len(tutarsiz)} tanesinde "
                 "ürün kaydıyla çelişen ifade var")
    s.append("")
    s.append(f"Üretilecek {len(gorseller)} sahne:")
    for g in gorseller[:6]:
        s.append(f"  · {g.get('ad')} ({g.get('oran')}) — “{g.get('ust_yazi') or ''}”")
    s.append("")
    s.append(f"Tam brief: {taban_url}/{parti}.md")
    s.append("ONAY = bu promptlarla görseller üretilsin (fatura burada başlar). "
             "RET = üretilmesin.")

    metin = "\n".join(s)
    ham = metin.encode("utf-8")
    if len(ham) <= AZAMI_GEREKCE:
        return metin
    return ham[:AZAMI_GEREKCE].decode("utf-8", "ignore") + "\n…(kırpıldı)"


def onay_ozeti(inceleme: dict[str, Any], parti: str,
               taban_url: str = "/kreatif") -> str:
    """Sahibin onay kuyruğunda göreceği metin.

    🔴 Bu metin KARARIN KENDİSİ DEĞİL, karara götüren şeydir. Sahip görsele
    bakarak karar verir, bu özeti okuyarak değil -- o yüzden her satırda
    görselin bağlantısı var ve ekip görüşlerinin uzun gerekçeleri buraya
    KOPYALANMAZ (zaten 2000 bayta sığmaz).
    """
    # 🔴 GÖRSEL BAĞLANTILARI 404 VERİYORDU. `loop.py` buraya brief partisini
    # geçiyor (`hydravie-20260921-1307`), görseller ise `<parti>-gorseller/`
    # klasöründe duruyor. Bağlantı `/kreatif/<parti>/01-1x1.jpg` diye
    # kuruluyordu ve o yol YOK. Onay ekranında tıklanmayan bir görsel,
    # görselsiz bir onaydır.
    klasor = parti if parti.endswith("-gorseller") else f"{parti}-gorseller"
    kareler = inceleme.get("gorseller") or []
    gecen = sum(1 for g in kareler if g.get("direktor_karari") == "GECER")
    satirlar = [
        f"{inceleme.get('urun') or '?'} için üretilen {len(kareler)} reklam "
        "görseli yayına uygun mu?",
        "",
        f"parti  : {parti}",
        f"direktör: {gecen}/{len(kareler)} kare geçti "
        f"({len(kareler) - gecen} tanesinde ekip itirazı var)",
        "",
    ]
    for g in kareler:
        karar = str(g.get("direktor_karari") or "?")
        olcum = g.get("olcum") or {}
        not_ = ""
        if olcum.get("beyaz_gecti") is False:
            not_ = f" [ÖLÇÜM: beyaz {olcum.get('beyaz_sapma'):+} kaymış]"
        elif olcum.get("urun_oran_gecti") is False:
            oran = (olcum.get("urun_oran") or 0) * 100
            not_ = f" [ÖLÇÜM: ürün karenin %{oran:.0f}'i]"
        satirlar.append(
            f"{ISARET.get(karar, '?')} {g.get('dosya')} ({g.get('oran')}) "
            f"{karar}{not_}\n"
            f"   “{g.get('ust_yazi') or ''}”\n"
            f"   {taban_url}/{klasor}/{g.get('dosya')}")
    satirlar.append("")
    satirlar.append(
        "ONAY = bu görseller yayına verilebilir. RET = verilmesin, yeniden üretilsin.")
    # 🔴 KLASÖR BAĞLANTISI VERİLMEZ. Panel dizin listesi sunmuyor
    # (`_route_kreatif` yalnız DOSYA servis eder), yani `/etiket-kontrol/`
    # bağlantısı giriş yapmış kullanıcıda 404 verirdi. Kırık bağlantı,
    # bağlantı olmamasından kötüdür: tıklayan kişi kontrolü yaptığını sanır.
    # Yakın planlar KREATİF sekmesinde her karenin altında duruyor.
    satirlar.append(
        "🔴 Ambalaj yazısının doğruluğu MAKİNEYLE DOĞRULANAMAZ "
        "(görme modeli bozuk harfi kafasında düzeltiyor). Onaydan önce "
        "KREATİF sekmesinden her karenin “ambalaj yakın planı”na bakın.")

    # Bayt sınırına göre kırp, karakter sınırına göre değil.
    metin = "\n".join(satirlar)
    ham = metin.encode("utf-8")
    if len(ham) <= AZAMI_GEREKCE:
        return metin
    return ham[:AZAMI_GEREKCE].decode("utf-8", "ignore") + "\n…(kırpıldı)"

