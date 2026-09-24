"""36 ürünün satış odaklı bilgi dosyasını GERÇEK VERİDEN üretir.

NEDEN ÜRETİCİ, NEDEN ELLE YAZMIYORUM
Katalogda 36 ürün var, derin bilgi dosyası yalnız 5'inde. Kalan 31'i kendi
bilgimden yazmak UYDURMA olurdu: bir dermokozmetik ürünün ne içerdiğini ve ne
dediğini ben bilemem, kaynak bilir. Bu betik her cümleyi ölçülmüş kaynaktan
türetir ve türetemediği yeri "İNSAN DOLDURUR" diye işaretler.

KAYNAKLAR (hepsi ölçülmüş, hiçbiri varsayım)
  mart.urun_karti   Wix açıklaması, fiyat, stok, Trendyol fiyatı, maliyet
                    Wix fiyat/stok OTORİTESİDİR (bkz. migration 007).
  jarvis.compliance TİTCK iddia denetçisi

ANAHTAR FİKİR -- SATIŞ CÜMLELERİ UYDURULMAZ, AYIKLANIR
"Satışta söylenebilir" bölümündeki her cümle, YAYINDAKI Wix açıklamasından
alınır ve mevzuat denetçisinden TEMİZ geçmiş olanlar arasından seçilir.
Yani cümleler hem gerçek (yayında duruyor) hem güvenli (denetimden geçti).
Uydurmaya gerek kalmaz.

Aynı tarama yayındaki metnin KENDİ kusurlarını da bulur: Wix'te duran bir
cümle mevzuata aykırıysa bu dosyada uyarı olarak görünür. Bu bir yan ürün
değil, işin en değerli çıktılarından biri.

ELLE YAZILMIŞ 5 DOSYAYA DOKUNULMAZ
vireon, femisia, intimblanc, liftelle, dermavasc dosyaları insan yargısı ve
eski katalog iç bilgisi taşıyor. Üretilmiş metin onların yerine geçemez.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import unicodedata

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import compliance  # noqa: E402

KNOWLEDGE = pathlib.Path("/opt/lcarlie/jarvis-phase2/knowledge")
ELLE_YAZILAN = {"vireon", "femisia", "intimblanc", "liftelle", "dermavasc"}

SORGU = r"""
\pset format unaligned
\pset tuples_only on
SELECT json_agg(row_to_json(t)) FROM (
  SELECT urun_adi, sku, aciklama_duz, wix_satis, wix_liste, wix_stok,
         wix_yayinda, trendyolda_var, trendyol_satis, birim_maliyet,
         maliyet_kaynagi, en_dusuk_marj
  FROM mart.urun_karti ORDER BY urun_adi) t;
"""

# Wix açıklamalarının başına yapıştırılmış kargo bloğu; ürün bilgisi değil.
_KARGO = re.compile(
    r"Kargo\s*&?a?m?p?;?\s*Teslimat.*?(Ücretsiz gönderim|ucretsiz gonderim)",
    re.IGNORECASE | re.DOTALL)
_HTML = re.compile(r"&[a-z]+;|&#\d+;")
_BOSLUK = re.compile(r"\s+")
_ICINDEKILER = re.compile(
    r"(İçindekiler|Icindekiler|INCI|Ingredients)\s*[:：]?\s*(.{40,1200})",
    re.IGNORECASE | re.DOTALL)
_KULLANIM = re.compile(
    r"(Kullanım|Kullanim|Nasıl kullanılır|Nasil kullanilir)\s*[:：]?\s*(.{20,400})",
    re.IGNORECASE | re.DOTALL)


def slugla(ad: str) -> str:
    """Dosya adı için sadeleştirilmiş ilk sözcük. Mevcut dosyalarla aynı desen:
    'VIREON FOR MEN · Erkek Bakım Kremi' -> 'vireon'."""
    ilk = re.split(r"[ (·|]", ad.strip())[0]
    d = unicodedata.normalize("NFKD", ilk.lower())
    d = "".join(c for c in d if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", d.replace("ı", "i")) or "urun"


def temizle(ham: str) -> str:
    m = _KARGO.sub(" ", ham or "")
    m = _HTML.sub(" ", m)
    return _BOSLUK.sub(" ", m).strip()


def cumleler(metin: str) -> list[str]:
    return [c.strip() for c in compliance.sentences(metin) if len(c.strip()) > 25]


# 🔴 İKİ KEZ ÖLÇÜLEN HATA -- sınıflandırma açıklama metninden yapılamaz.
#
# 1. deneme: ad + açıklama -> 31 üründen 28'i "bebek ve çocuk". Sebep her
#    açıklamada duran "Çocukların ulaşamayacağı yerde saklayınız."
# 2. deneme: uyarıları eleyip tekrar -> bu sefer 10 ürün "güneş", çünkü
#    "Güneş ışığından uzak tutunuz." de her metinde var. LUCIDERM yüz
#    köpüğü, SERALIMBO gece kremi, CALMAROS tonik... hepsi güneş ürünü
#    sayıldı.
#
# Uyarı listesini büyütmek köstebek oyunu: açıklama metni yasal uyarı,
# saklama koşulu, kullanım talimatı ve kargo bilgisi taşıyor; bunların hepsi
# ürünle ilgisiz kelimeler içeriyor.
#
# KARAR: yalnız ÜRÜN ADI. Bu katalogda adlar zaten açıklayıcı --
# "(Güneş Kremi)", "(Ayak ve Tırnak Bakım Kremi)", "(Yüz Temizleme Köpüğü)".
# Ad söylemiyorsa sınıflandırmıyoruz. Yanlış kategori, kategorisizlikten
# kötüdür: ajanın ürünü yanlış kitleye önermesi demektir.

_KATEGORILER = (
    # Sıra önemli: en spesifik önce. "Bebek Vücut Losyonu" hem bebek hem vücut
    # geçiriyor; doğru cevap bebek.
    ("bebek ve çocuk", ("bebek", "çocuk", "baby", "mini")),
    ("hassas bölge", ("intim", "hassas bölge")),
    ("güneş", ("güneş kremi", "spf")),
    ("ağız ve diş", ("diş", "ağız", "smile")),
    ("saç", ("saç", "şampuan")),
    ("ayak ve tırnak", ("ayak", "tırnak")),
    ("göz çevresi", ("göz çevresi",)),
    ("dudak", ("dudak",)),
    ("yüz", ("yüz", "gece bakım", "nemlendirici yüz")),
    ("vücut ve masaj", ("masaj", "sporcu", "bacak", "vücut", "gerilme", "dekolte")),
)


def kategori(ad: str, metin: str) -> str:
    """YALNIZ ürün adına bakar. `metin` bilerek kullanılmıyor -- yukarıdaki
    iki ölçüm açıklama metninin sınıflandırma için elverişsiz olduğunu
    gösterdi. Ad söylemiyorsa sınıflandırmaz."""
    a = ad.lower()
    for etiket, isaretler in _KATEGORILER:
        if any(i in a for i in isaretler):
            return etiket
    return "İNSAN DOLDURUR"



# 🔴 ÜÇÜNCÜ ÖLÇÜM HATASI -- ilk iki sayı (45, sonra 25) YANLIŞTI.
#
# Sebep bende: compliance.review() bir metnin TAMAMI için tasarlanmış, ben onu
# cümle cümle çağırdım. Sonuç iki tür yanlış pozitif:
#
#   1. BELGE DÜZEYİ kurallar her cümlede ayrı ateşlendi. Güneş kremlerinde
#      "zorunlu ifade eksik" bulgusu 10 cümlenin 10'unda da göründü; oysa
#      eksiklik metnin bütününe ait tek bir olgu.
#   2. ZORUNLU GÜVENLİK UYARILARI iddia sanıldı. "Tahriş durumunda kullanımı
#      bırakınız" cümlesindeki "tahriş" kelimesi hastalık/durum adı olarak
#      yakalandı -- oysa o cümle mevzuatın KENDİSİNİN istediği uyarı.
#
# Doğrusu: belge düzeyi bulgular metnin tamamında BİR KEZ; cümle düzeyi
# bulgular cümle cümle; zorunlu uyarılar ise ne satış cümlesi ne kusur --
# ayrı bir küme.

_UYARI = re.compile(
    r"kullanımı?\s*(bırak|durdur|kesin)|kullanmayı\s*bırak|"
    r"uygulama(yınız|yin)|uygulanmamalı|"
    r"doktora\s*danış|doktorunuza\s*danış|hekime\s*başvur|"
    r"uzak\s*tut|saklayın|temasından\s*kaçın|yutulmamalı|"
    r"harici\s*kullanım|çocukların\s*(ula|eri)|"
    r"%100\s*koruma\s*sağlamaz|2\s*mg/cm|"
    r"test(ler)?le\s*değerlendiril", re.IGNORECASE)


def zorunlu_uyari(cumle: str) -> bool:
    """Mevzuatın kendisinin istediği uyarı/talimat cümlesi mi.

    Bunlar ne satış cümlesidir ne de düzeltilecek kusur. Wix'ten silinmeleri
    MEVZUATA AYKIRI olurdu -- denetçinin onlara takılması yanlış pozitiftir.
    """
    return bool(_UYARI.search(cumle))


# Bu kurallar metnin BUTUNUNE bakar: "zorunlu ibare eksik" bir cumlenin degil
# belgenin ozelligidir. Cumle cumle tarayinca SPF geçen her cumlede ayri ayri
# ateslendiler ve gercek bulgu gibi gorundu. Adlariyla ayriliyorlar -- kumeyi
# "tum bulgular eksi cumle bulgulari" diye hesaplamak yetmedi, cunku ayni kural
# iki duzeyde de ates ediyor.
BELGE_DUZEYI_KURALLAR = frozenset({
    "güneş koruyucu zorunlu ibare eksik",
    "hashtag tavanı",
})


def belge_bulgulari(metin: str):
    """Belge düzeyi kurallar: metnin TAMAMINDA bir kez."""
    return [f for f in compliance.review(metin).findings
            if f.rule in BELGE_DUZEYI_KURALLAR]


def dosya_uret(u: dict) -> tuple[str, str, dict]:
    ad = (u["urun_adi"] or "").strip()
    slug = slugla(ad)
    metin = temizle(u.get("aciklama_duz") or "")
    tum = cumleler(metin)

    # Üç küme, üçü de ayrı: satış cümlesi / gerçek kusur / zorunlu uyarı.
    temiz, kusurlu, uyarilar = [], [], []
    for c in tum:
        if zorunlu_uyari(c):
            uyarilar.append(c)          # ne satış cümlesi ne kusur
            continue
        r = compliance.review(c)
        # Belge duzeyi kurallari cumleden DUS: onlar zaten belge_bulgulari()'nda.
        cumle_bulgulari = [f for f in r.findings
                           if f.rule not in BELGE_DUZEYI_KURALLAR]
        if cumle_bulgulari:
            kusurlu.append((c, cumle_bulgulari))
        else:
            temiz.append(c)
    belge = belge_bulgulari(metin)

    ic = _ICINDEKILER.search(metin)
    kul = _KULLANIM.search(metin)

    wix = u.get("wix_satis")
    liste = u.get("wix_liste")
    ty = u.get("trendyol_satis") if u.get("trendyolda_var") else None
    stok = u.get("wix_stok")
    marj = u.get("en_dusuk_marj")

    # 🔴 ÖLÇÜLDÜ: ince anahtar listesi yanlis urunu getiriyor.
    # Ilk hali {slug, BUYUK_HARFLI_MARKA} idi. Sonuc:
    #   "sporcu bakim kremi"    -> BABYDENT   (dogrusu KINESIS+)
    #   "bebek bez bolgesi"     -> BABYDENT   (dogrusu MINISOOTH)
    # Musteri urunu adiyla degil TARIFIYLE ariyor. Urun adinin parantez ici
    # tanimi ("Sporcu Bakim Kremi", "Bebek Bez Bolgesi Bakim Kremi") tam o
    # tarifi tasiyor ve zaten gercek veri -- uydurma degil.
    # 🔴 IKINCI OLCUM: 12 tarif sorgusunun 4'u yanlis urun getirdi.
    #   "sac bakim yagi"    -> BABYDENT   (dogrusu HAIR NOURISHER)
    #   "agiz bakim spreyi" -> EASYCOMB   (dogrusu ORAGARDE)
    # Sebep bu projenin klasik tuzagi: musteri ASCII yazar ("sac", "agiz"),
    # anahtar Turkce yazilidir ("saç", "ağız") ve esleme SESSIZCE bos doner.
    # Her anahtarin ASCII karsiligi da listeye girer.
    _DOLGU = {"ve", "icin", "için", "ile", "bir", "ozel", "özel"}
    _ASCII = str.maketrans("çğıöşüâî", "cgiosuai")

    def _ascii(w: str) -> str:
        return w.translate(_ASCII)

    ad_sozcukleri = {w.lower() for w in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşüÂÎ]{3,}", ad)}
    ad_sozcukleri = {w.replace("İ", "i").lower() for w in ad_sozcukleri}
    # BRIGHT SMILE'in adinda Turkce tanim YOK -- "dis macunu" sorgusu onu
    # bulamiyordu. Urunun kendi ilk cumlesi tanimi tasiyor ve gercek veri.
    ilk_cumle = temiz[0] if temiz else ""
    # 🔴 En az 4 harf kurali Turkcede is gormuyor: "dis", "goz", "sac", "cilt"
    # hepsi kisa ve hepsi urunun ne oldugunu soyluyor. BRIGHT SMILE'in ilk
    # cumlesi "(Dogal Icerikli Beyazlatici Dis Macunu)" ile basliyor ama "Dis"
    # 3 harf oldugu icin eleniyordu; "dis macunu" sorgusu urunu bulamiyordu.
    tanim = {w.lower() for w in re.findall(
        r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,}", ilk_cumle[:160])}
    tanim -= {"carlie", "gunluk", "günlük", "uzere", "üzere", "rutine", "rutini",
              "gelistirilmis", "geliştirilmiş", "formule", "formüle", "edilmis",
              "edilmiş", "olarak", "yonelik", "yönelik", "bakim", "bakım"}
    tum_anahtar = {slug} | ad_sozcukleri | set(sorted(tanim, key=len)[:10])
    tum_anahtar |= {_ascii(w) for w in tum_anahtar}
    anahtarlar = sorted(tum_anahtar - _DOLGU - {_ascii(d) for d in _DOLGU})
    kat = kategori(ad, metin)

    L: list[str] = []
    A = L.append
    A("---")
    A(f"konu: {ad} ürün bilgisi")
    A(f"anahtar: [{', '.join(anahtarlar)}, {kat if kat != 'İNSAN DOLDURUR' else 'ürün'}]")
    A("gizlilik: ic-bilgi")
    A("kaynak: mart.urun_karti (Wix yayındaki metin) + jarvis.compliance taraması")
    A("uretim: tools/urun-bilgi-uret.py -- ELLE DÜZENLENEBİLİR, yeniden üretim üzerine yazar")
    A("---")
    A("")
    A(f"# {ad}")
    A("")
    fiyat = f"**{wix:,.0f} TL**".replace(",", ".") if wix else "**fiyat okunamadı**"
    A(f"`{slug}` · {fiyat}")
    A("")

    A("## Tek cümlede")
    A(temiz[0] if temiz else "İNSAN DOLDURUR — yayındaki metinden temiz cümle çıkmadı.")
    A("")

    A("## Kim için")
    A(f"Kategori: **{kat}**")
    A("")
    A("Hedef alıcı ve hangi durumda önerileceği: **İNSAN DOLDURUR.** Bu, Wix"
      " açıklamasından türetilemez; satış deneyiminden gelir.")
    A("")

    A("## Fiyat ve platform")
    A("")
    A("| | |")
    A("|---|---|")
    if wix:
        A(f"| Wix satış | {wix:,.0f} TL |".replace(",", "."))
    if liste and wix and float(liste) > float(wix):
        A(f"| Wix liste (üstü çizili) | {liste:,.0f} TL |".replace(",", "."))
    if ty:
        fark = ((float(ty) - float(wix)) / float(wix) * 100) if wix else 0
        A(f"| Trendyol | {ty:,.0f} TL ({fark:+.0f}%) |".replace(",", "."))
    else:
        A("| Trendyol | listede yok |")
    if stok is not None:
        A(f"| Wix stok | {stok} |")
    if marj is not None:
        A(f"| En düşük marj | %{marj} |")
    A("")
    if u.get("maliyet_kaynagi") == "ELLE":
        A("> Maliyet **ölçülmedi**, elle girilmiş tahmin (₺400). Marj buna dayanıyor,"
          " kesin değildir.")
        A("")

    A("## Satışta söylenebilir")
    A("")
    A("Aşağıdaki cümleler **yayındaki Wix metninden** alındı ve mevzuat"
      " denetçisinden **temiz** geçti. Olduğu gibi kullanılabilir.")
    A("")
    if temiz:
        for c in temiz[:8]:
            A(f"- {c}")
    else:
        A("- İNSAN DOLDURUR — temiz cümle çıkmadı.")
    A("")

    if kul:
        A("## Kullanım")
        A(_BOSLUK.sub(" ", kul.group(2)).strip()[:300])
        A("")

    if ic:
        A("## İçindekiler")
        A(_BOSLUK.sub(" ", ic.group(2)).strip()[:900])
        A("")

    A("## ⚠️ Bu üründe dikkat")
    A("")
    if kusurlu:
        A("Yayındaki metnin şu cümleleri denetimden **geçmedi**. Müşteri yanıtına,"
          " reklama veya caption'a taşınmaz — ve Wix'te gözden geçirilmeli:")
        A("")
        for c, bulgular in kusurlu[:6]:
            b = bulgular[0]
            A(f"- **{b.label}** · {b.rule} · eşleşen: *{b.matched}*")
            A(f"  > {c[:170]}")
        A("")
    if belge:
        A("Metnin **bütününe** ait bulgular:")
        A("")
        for b in belge[:5]:
            A(f"- **{b.label}** · {b.rule} · *{b.matched}*")
            if b.remedy:
                A(f"  → {b.remedy}")
        A("")
    if not kusurlu and not belge:
        A("Yayındaki metinde denetim bulgusu yok.")
        A("")

    if uyarilar:
        A("### Zorunlu uyarılar (silinmez)")
        A("")
        A("Bunlar mevzuatın kendisinin istediği cümleler. Satış metni **değildir**,"
          " ama Wix'ten kaldırılmaları da mevzuata aykırı olur.")
        A("")
        for c in uyarilar[:6]:
            A(f"- {c[:150]}")
        A("")

    A("## Eksik bilgi")
    A("")
    A("- Hedef alıcı ve öneri durumu — **İNSAN DOLDURUR**")
    A("- Sık gelen itirazlar ve cevapları — **İNSAN DOLDURUR**")
    A("- Ürün bilgilendirme dosyası (ÖBF) bağlantısı — **İNSAN DOLDURUR**")
    if not ic:
        A("- İçindekiler listesi yayındaki metinde bulunamadı — **İNSAN DOLDURUR**")
    A("")

    ozet = {"ad": ad, "slug": slug, "temiz": len(temiz), "kusurlu": len(kusurlu),
            "uyari": len(uyarilar), "belge": len(belge),
            "bloklu": sum(1 for _, f in kusurlu for x in f if x.label == compliance.BLOCKED),
            "icindekiler": bool(ic), "kategori": kat}
    return slug, "\n".join(L) + "\n", ozet


def main() -> int:
    ham = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n"],
        input=SORGU, capture_output=True, text=True, timeout=120).stdout
    veri = None
    for satir in ham.splitlines():
        s = satir.strip()
        if s.startswith("["):
            veri = json.loads(s)
            break
    if not veri:
        print("VERI OKUNAMADI -- dosya YAZILMADI")
        print(ham[:400])
        return 1

    yazilan, atlanan, ozetler = 0, [], []
    for u in veri:
        slug, icerik, ozet = dosya_uret(u)
        if slug in ELLE_YAZILAN:
            atlanan.append(slug)
            continue
        (KNOWLEDGE / f"30-urun-{slug}.md").write_text(icerik, encoding="utf-8")
        yazilan += 1
        ozetler.append(ozet)

    print(f"yazilan: {yazilan}   elle yazilmis (atlandi): {len(atlanan)} -> {', '.join(sorted(atlanan))}")
    print()
    print(f"  {'urun':<44} {'satis':>5} {'BLOKLU':>6} {'belge':>5} {'uyari':>5}  kategori")
    for o in sorted(ozetler, key=lambda x: (-x["bloklu"], -x["belge"])):
        print(f"  {o['ad'][:43]:<44} {o['temiz']:>5} {o['bloklu']:>6} {o['belge']:>5} "
              f"{o['uyari']:>5}  {o['kategori']}")
    print()
    print(f"TOPLAM gercek bloklu cumle : {sum(o['bloklu'] for o in ozetler)}")
    print(f"TOPLAM belge duzeyi bulgu  : {sum(o['belge'] for o in ozetler)}")
    print(f"TOPLAM zorunlu uyari       : {sum(o['uyari'] for o in ozetler)}  (kusur DEGIL)")
    print(f"Icindekiler bulunamayan urun: {sum(1 for o in ozetler if not o['icindekiler'])}")
    print(f"Kategorisi belirsiz urun: {sum(1 for o in ozetler if o['kategori'] == 'İNSAN DOLDURUR')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
