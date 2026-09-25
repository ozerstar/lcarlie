#!/usr/bin/env python3
"""KARGO ETİKETİ — BasitKargo etiketlerini HB-1006 sayfasına dizer.

Sahib 21.09.2026: *"biz kargo etiketlerini normal printerdan alıyoruz ve
Herboy marka HB-1006 99.1x93.1mm etiketlerini kullanıyoruz… bu şablonu
alıp etiketler buna göre yerleşimi yapılacak."*

🔴 ÖLÇÜLER TAHMİN EDİLMEDİ, ŞABLONDAN OKUNDU.
`C:\\Users\\ozery\\Downloads\\HB-1006.doc` Word COM ile açılıp geometrisi
çıkarıldı. İlk okumada tek sütun ölçülüp "hepsi aynı" varsayılmıştı ve
3 × 99.06 = 297 mm çıktı -- sayfaya sığmıyordu. Her sütun tek tek
ölçülünce gerçek yapı göründü:

    sütun 1: 99.06 mm  (etiket)
    sütun 2:  2.95 mm  (BOŞLUK -- etiket değil)
    sütun 3: 99.06 mm  (etiket)
    satır  : 93.13 mm, sabit yükseklik (HeightRule=2)
    kenar  : üst 10 · alt 0 · sol 5.01 · sağ 5.01 mm

Yani sayfada 6 etiket var, 9 değil. Ortadaki sütunu etiket sanmak
baskıyı tamamen kaydırırdı.

🔴 ETİKETİ BİZ ÇİZMİYORUZ. Her hücreye BasitKargo'nun KENDİ ürettiği
etiket PNG'si konur (`get_label`). Taşıyıcının resmî etiketi odur;
barkodu yeniden çizmek okunamayan bir baskı riski demekti.

Çıkış: 0=belge üretildi · 1=hata · 2=etiket alınamadı
"""
from __future__ import annotations

import argparse
import base64
import io
import os
import sys
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from docx import Document  # noqa: E402
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Mm, Pt  # noqa: E402

from jarvis.basitkargo import Kargo, KargoHatasi  # noqa: E402

# --- HB-1006 geometrisi (şablondan ölçüldü, 21.09.2026) ---
SAYFA_EN, SAYFA_BOY = 210.0, 297.0
KENAR_UST, KENAR_ALT, KENAR_SOL, KENAR_SAG = 10.0, 0.0, 5.01, 5.01
ETIKET_EN, ETIKET_BOY = 99.06, 93.13
BOSLUK_EN = 2.95
SUTUN = 2          # etiket sütunu (aradaki boşluk sütunu sayılmaz)
SATIR = 3
SAYFADA = SUTUN * SATIR   # 6

CIKTI_KOK = Path(os.environ.get("KARGO_ETIKET_DIR", str(KOK / "state" / "kargo-etiket")))


def etiket_getir(k: Kargo, siparis_id: str) -> list[bytes]:
    """Bir siparişin etiket PNG'leri (paket başına bir tane)."""
    sonuc = k.cagir("get_label", {"orderId": siparis_id})
    gorseller = sonuc.get("gorseller") or []
    cikti = []
    for g in gorseller:
        try:
            cikti.append(base64.b64decode(g.get("veri") or ""))
        except Exception:  # noqa: BLE001
            continue
    return cikti


def _sayfa_kur(belge: Document) -> None:
    b = belge.sections[0]
    b.page_width, b.page_height = Mm(SAYFA_EN), Mm(SAYFA_BOY)
    b.top_margin, b.bottom_margin = Mm(KENAR_UST), Mm(KENAR_ALT)
    b.left_margin, b.right_margin = Mm(KENAR_SOL), Mm(KENAR_SAG)
    # 🔴 Üstbilgi/altbilgi payı sıfırlanır: varsayılan 12.7 mm, ilk satırı
    # aşağı iter ve bütün sayfa bir etiket boyu kayar.
    b.header_distance, b.footer_distance = Mm(0), Mm(0)


def _tablo_kur(belge: Document):
    """3 sütun (etiket · boşluk · etiket) × 3 satır, sabit ölçülerle."""
    t = belge.add_table(rows=SATIR, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    t.autofit = False
    genislikler = (Mm(ETIKET_EN), Mm(BOSLUK_EN), Mm(ETIKET_EN))
    for satir in t.rows:
        satir.height = Mm(ETIKET_BOY)
        # 🔴 EXACTLY şart: AT_LEAST olursa içerik hücreyi büyütür ve
        # alttaki bütün etiketler kayar -- kağıt israfı ve yanlış baskı.
        satir.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
        for i, h in enumerate(satir.cells):
            h.width = genislikler[i]
            # 🔴 `cell.width` TEK BASINA YETMEDI: uretilen belgede bosluk
            # sutunu 2.95 yerine 4.16 mm cikti (olculdu). Word, tablo
            # izgarasini ayrica `tblGrid` icinde tutuyor; ikisi
            # uyusmazsa izgara kazaniyor. `_izgara_sabitle` onu da yazar.
            # Hücre iç boşluğu şablonda sol/sağ 0.26, üst/alt 0.
            p = h.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
    _hucre_payi_sifirla(t)
    _izgara_sabitle(t, genislikler)
    return t


def _izgara_sabitle(tablo, genislikler) -> None:
    """`tblGrid` sütun genişliklerini birebir yazar.

    python-docx `cell.width` verse de Word tablo ızgarasını ayrı tutar;
    ızgara ile hücre uyuşmazsa ızgara kazanır ve sütunlar kayar.
    Ölçüldü: boşluk sütunu 2.95 istendi, 4.16 çıktı.
    """
    from docx.oxml.ns import qn

    xml = tablo._tbl
    izgara = xml.find(qn("w:tblGrid"))
    if izgara is None:
        return
    sutunlar = izgara.findall(qn("w:gridCol"))
    # strict=False acikca yaziliyor: sutun sayisi XML'den, genislikler
    # cagirandan geliyor ve esit olduklari DOGRULANMADI. strict=True burada
    # canli bir kargo etiketi akisini dusurebilirdi; kirpma davranisi
    # bilerek korunuyor.
    for s, g in zip(sutunlar, genislikler, strict=False):
        # w:w yirmide bir punto (dxa) cinsindendir.
        s.set(qn("w:w"), str(int(g.twips)))
    # Tablo duzeni SABIT olsun; otomatik duzen icerige gore genislik
    # yeniden dagitir ve olculeri bozar.
    ozellik = xml.find(qn("w:tblPr"))
    if ozellik is not None:
        mevcut = ozellik.find(qn("w:tblLayout"))
        if mevcut is None:
            from docx.oxml import OxmlElement
            mevcut = OxmlElement("w:tblLayout")
            ozellik.append(mevcut)
        mevcut.set(qn("w:type"), "fixed")


# Hücrenin içine bırakılan pay: kenara sıfır yapıştırmak, yazıcıların
# kenar toleransında etiketin kırpılmasına yol açıyor.
PAY_MM = 1.0


def _sigdir_olcek(png: bytes) -> tuple[float, float]:
    """Etiketi hücreye SIĞDIRAN ölçü. En-boy oranı korunur.

    🔴 BU DÜZELTME ÖLÇÜMDEN DOĞDU. İlk sürüm yalnız genişliğe göre
    ölçekliyordu (`width=Mm(99)`). Üretilen belge Word ile ölçüldüğünde
    görseller 125.02 ve 117.67 mm YÜKSEKLİKTE çıktı; hücre ise 93.13 mm
    ve satır yüksekliği EXACTLY. Yani her etiketin ALTI KESİLECEKTİ --
    barkodun durduğu yer.

    BasitKargo etiketi dikey (≈98x125), HB-1006 hücresi ise yatay
    (99x93). Bu yüzden sıkışan kenar YÜKSEKLİKTİR ve ölçek ondan
    hesaplanmalıdır. İki kenardan küçük olan oran alınır.
    """
    try:
        from PIL import Image
        with Image.open(io.BytesIO(png)) as im:
            px_en, px_boy = im.size
    except Exception:  # noqa: BLE001
        # Ölçü okunamazsa hücreye TAM sığan güvenli kutu kullanılır;
        # oran bozulabilir ama kesilme olmaz.
        return ETIKET_EN - PAY_MM, ETIKET_BOY - PAY_MM
    if not px_en or not px_boy:
        return ETIKET_EN - PAY_MM, ETIKET_BOY - PAY_MM
    hedef_en, hedef_boy = ETIKET_EN - PAY_MM, ETIKET_BOY - PAY_MM
    olcek = min(hedef_en / px_en, hedef_boy / px_boy)
    return round(px_en * olcek, 2), round(px_boy * olcek, 2)


def belge_uret(etiketler: list[tuple[str, bytes]], cikti: Path) -> dict:
    """Etiketleri sayfalara böler ve .docx yazar."""
    belge = Document()
    _sayfa_kur(belge)

    # Varsayılan paragraf boşluklarını sıfırla: 8 pt boşluk bile hücreyi
    # taşırıp satırı kaydırıyor.
    stil = belge.styles["Normal"]
    stil.paragraph_format.space_before = Pt(0)
    stil.paragraph_format.space_after = Pt(0)
    stil.paragraph_format.line_spacing = 1.0

    sayfa_sayisi = 0
    for bas in range(0, len(etiketler), SAYFADA):
        grup = etiketler[bas:bas + SAYFADA]
        if sayfa_sayisi:
            belge.add_page_break()
        t = _tablo_kur(belge)
        for n, (_ref, png) in enumerate(grup):
            satir, sutun = divmod(n, SUTUN)
            hucre = t.cell(satir, 0 if sutun == 0 else 2)
            p = hucre.paragraphs[0]
            en_mm, boy_mm = _sigdir_olcek(png)
            p.add_run().add_picture(io.BytesIO(png),
                                    width=Mm(en_mm), height=Mm(boy_mm))
        sayfa_sayisi += 1

    cikti.parent.mkdir(parents=True, exist_ok=True)
    belge.save(str(cikti))
    return {"dosya": str(cikti), "etiket": len(etiketler), "sayfa": sayfa_sayisi}



# Şablonda ölçülen hücre iç boşluğu: sol/sağ 0.26 mm, üst/alt 0.
HUCRE_PAYI_MM = 0.26


def _hucre_payi_sifirla(tablo) -> None:
    """Tablo hücrelerinin iç boşluğunu şablondaki değere indirir.

    🔴 BOŞLUK SÜTUNUNUN GERÇEK SEBEBİ BUYDU. `tblGrid`'e 2.95 mm yazmak
    yetmedi; ölçümde hep 4.16 mm çıktı. Neden: Word'ün varsayılan hücre
    iç boşluğu sol ve sağ 1.9'ar mm'dir ve bir sütun, kendi iç
    boşluğunun toplamından (3.8 mm) dar olamaz. Yani sınırı koyan
    ızgara değil, iç boşluktu.

    Bunun bedeli yalnız ortadaki 1.2 mm değil: 99.06 + 4.16 + 99.06 =
    202.28 mm, kullanılabilir genişlik ise 199.98 mm. Tablo sağ kenarı
    2.3 mm taşıyor ve SAĞDAKİ etiket sütunu kayıyor -- baskı yamuk
    çıkardı.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm

    ozellik = tablo._tbl.find(qn("w:tblPr"))
    if ozellik is None:
        return
    mevcut = ozellik.find(qn("w:tblCellMar"))
    if mevcut is not None:
        ozellik.remove(mevcut)
    pay = OxmlElement("w:tblCellMar")
    for kenar, mm in (("top", 0.0), ("left", HUCRE_PAYI_MM),
                      ("bottom", 0.0), ("right", HUCRE_PAYI_MM)):
        e = OxmlElement(f"w:{kenar}")
        e.set(qn("w:w"), str(int(Mm(mm).twips)))
        e.set(qn("w:type"), "dxa")
        pay.append(e)
    ozellik.append(pay)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="BasitKargo etiketlerini HB-1006 sayfasına dizer")
    ap.add_argument("siparis", nargs="*", help="BasitKargo sipariş id'leri")
    ap.add_argument("--son", type=int, default=0,
                    help="son N kodlanmış gönderinin etiketini al")
    ap.add_argument("--cikti", default=None)
    a = ap.parse_args()

    k = Kargo()
    idler = list(a.siparis)

    if a.son:
        # Kodlanmış (barkodu olan) gönderiler; etiketi olmayanı istemek
        # boş sayfa üretirdi.
        try:
            r = k.cagir("list_shipments", {"size": a.son, "status": "READY_TO_SHIP"})
        except KargoHatasi as hata:
            print(f"liste alinamadi: {hata}", file=sys.stderr)
            return 1
        veri = r.get("veri") or {}
        for s in (veri.get("items") or [])[:a.son]:
            if s.get("id"):
                idler.append(str(s["id"]))

    if not idler:
        print("sipariş id verilmedi (ya da --son ile bulunamadı)", file=sys.stderr)
        return 2

    etiketler: list[tuple[str, bytes]] = []
    for sid in idler:
        try:
            pngler = etiket_getir(k, sid)
        except KargoHatasi as hata:
            print(f"  {sid}: etiket alınamadı — {str(hata)[:140]}", file=sys.stderr)
            continue
        if not pngler:
            print(f"  {sid}: etiket yok (kodlanmamış olabilir)", file=sys.stderr)
            continue
        for png in pngler:
            etiketler.append((sid, png))
        print(f"  {sid}: {len(pngler)} etiket")

    if not etiketler:
        print("hiç etiket alınamadı", file=sys.stderr)
        return 2

    damga = datetime.now().strftime("%Y%m%d-%H%M")
    cikti = Path(a.cikti) if a.cikti else CIKTI_KOK / f"etiket-{damga}.docx"
    sonuc = belge_uret(etiketler, cikti)
    print(f"\n{sonuc['etiket']} etiket · {sonuc['sayfa']} sayfa")
    print(sonuc["dosya"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
