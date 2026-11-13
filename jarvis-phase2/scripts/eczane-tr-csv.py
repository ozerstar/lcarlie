"""ECZANELER-TEMIZ.xlsx -> eczane_tr.csv (il, eczane, eczaci, telefon, adres, oncelik).

Kaynaktaki il yazımı tutarsız ('ISTANBUL', 'IZMİR', 'ŞANLIURFA'); resmî 81 il
adına ASCII anahtarla eşlenir. Eşlenemeyen il HATA verir — sessizce yanlış
ile yazmak, o ilin kampanyasını boş gösterirdi.
"""
import csv
import sys

import openpyxl

ILLER = """Adana Adıyaman Afyonkarahisar Ağrı Aksaray Amasya Ankara Antalya Ardahan Artvin
Aydın Balıkesir Bartın Batman Bayburt Bilecik Bingöl Bitlis Bolu Burdur Bursa Çanakkale
Çankırı Çorum Denizli Diyarbakır Düzce Edirne Elazığ Erzincan Erzurum Eskişehir Gaziantep
Giresun Gümüşhane Hakkari Hatay Iğdır Isparta İstanbul İzmir Kahramanmaraş Karabük Karaman
Kars Kastamonu Kayseri Kilis Kırıkkale Kırklareli Kırşehir Kocaeli Konya Kütahya Malatya
Manisa Mardin Mersin Muğla Muş Nevşehir Niğde Ordu Osmaniye Rize Sakarya Samsun Şanlıurfa
Siirt Sinop Şırnak Sivas Tekirdağ Tokat Trabzon Tunceli Uşak Van Yalova Yozgat Zonguldak""".split()

# Sahip sırası: Ankara -> büyükşehirler (nüfusa göre) -> diğer iller.
BUYUKSEHIR = ["İstanbul", "İzmir", "Bursa", "Antalya", "Konya", "Adana", "Şanlıurfa",
              "Gaziantep", "Kocaeli", "Mersin", "Diyarbakır", "Hatay", "Manisa", "Kayseri",
              "Samsun", "Balıkesir", "Kahramanmaraş", "Van", "Aydın", "Tekirdağ", "Sakarya",
              "Denizli", "Muğla", "Eskişehir", "Mardin", "Malatya", "Trabzon", "Erzurum",
              "Ordu"]


def anahtar(s):
    s = (s or "").strip().upper()
    return s.translate(str.maketrans("ÇĞİIÖŞÜÂÎçğıiöşü", "CGIIOSUAICGIIOSU")).replace(" ", "")


IL = {anahtar(i): i for i in ILLER}
assert len(IL) == 81


def oncelik(il):
    if il == "Ankara":
        return 1
    if il in BUYUKSEHIR:
        return 2 + BUYUKSEHIR.index(il)
    return 100


kaynak, hedef = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(kaynak, read_only=True)
satirlar = wb["Eczaneler"].iter_rows(values_only=True)
next(satirlar)
n, bilinmeyen = 0, set()
with open(hedef, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    for r in satirlar:
        il_ham, eczane, eczaci, tel, _, adres = r[:6]
        if not il_ham or not eczane:
            continue
        il = IL.get(anahtar(il_ham))
        if not il:
            bilinmeyen.add(il_ham)
            continue
        w.writerow([il, str(eczane).strip(), (eczaci or "").strip(), (tel or "").strip(),
                    (adres or "").strip(), oncelik(il)])
        n += 1
if bilinmeyen:
    sys.exit("eşlenemeyen il: %s" % sorted(bilinmeyen))
print(n, "satır")
