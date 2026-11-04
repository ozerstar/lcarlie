#!/usr/bin/env python3
"""Idefix destek talebi metnini veriden uretir (barkodlar elle yazilmaz)."""
import json

d = json.load(open("/tmp/destek-veri.json", encoding="utf-8"))


def liste(xs):
    return "\n".join(f"   {b}  {a}" for b, a in xs)


CIZGI = "-" * 72

metin = f"""Konu: Katalog marka ve kategori düzeltmesi talebi - L'CARLIE (Satıcı ID 22204)

Sayın idefix Satıcı Destek Ekibi,

LEMOS Medikal Sağlık (Satıcı ID 22204) olarak L'CARLIÉ markalı kozmetik ürünlerin
marka sahibiyiz. Ürünlerimizin barkodları 8684869 ile başlayan kendi GS1 kaydımıza
aittir. 22.10.2026 tarihinde panel üzerinden "L'CARLIE" için marka ekleme talebi
oluşturduk (Marka Ekleme Talebi, 1 kayıt, hatasız yüklendi).

Ürünlerimizi listelerken dört konuda desteğinize ihtiyacımız var.

{CIZGI}
1) KATALOG MARKASININ DÜZELTİLMESİ

Kendi ürünlerimizi gönderdiğimizde talepler "BRAND_FAILED_TO_MATCH" hatasıyla
reddediliyor; barkodlarımız katalogda bize ait olmayan iki marka altında kayıtlı:

 - "MC" (marka ID 20027051) - 18 barkod
{liste(d['MC'])}

 - "Lc.Imeeke" (marka ID 20109748) - 12 barkod
{liste(d['Lc'])}

Bu kayıtların katalog markasının "L'CARLIE" olarak düzeltilmesini talep ediyoruz.
Not: "MC" markası altındaki listelemeleri yapan Mcaris mağazası bizim yetkili
satıcımızdır; düzeltmeye itirazı yoktur ve gerekirse kendisi de teyit edecektir.

{CIZGI}
2) YANLIŞ ÜRÜN EŞLEŞMESİ OLAN İKİ BARKOD

Aşağıdaki iki barkodumuz katalogda BAŞKA bir ürünün sayfasına bağlanmış durumda.
Yanlış ürünün satılmaması için ikisini de satışa kapattık.

 - 8684869609097 - bizdeki ürün: SUNACNEA Güneş Kremi SPF 30, 50 ml
   Bağlandığı katalog ürünü: "L'CARLIE CALMAROS … Tonik Sprey" (kategori: Tonik)

 - 8684869609301 - bizdeki ürün: BUGUARD Bitkisel Vücut Spreyi, 100 ml
   Bağlandığı katalog ürünü: "L'CARLIE SOFTGUARD … Akar Spreyi"
   (kategori: Sinek İlacı ve Kovucu)

Bu iki barkodun doğru ürünlerle eşleştirilmesini, ya da eşleşmenin kaldırılarak
tarafımızca yeniden oluşturulabilmesini talep ediyoruz.

{CIZGI}
3) KATEGORİ DÜZELTMESİ

Aşağıdaki ürünlerin katalog kategorisi ürün türüyle uyumlu değil. Satıcı
panelindeki "Ürün Bilgisi Güncelleme" talebinde kategori alanı bulunmadığından
düzeltmeyi tarafınızdan talep ediyoruz.

 - 8684869609547  KINESIS+ Sporcu Bakım Kremi
 - 8684869609516  DERMAMOVERA Bitkisel Masaj ve Bakım Kremi
 - 8684869609554  DERMARNICA Arnika Özlü Bitkisel Bakım Kremi
   Üçü de krem formundadır. "Masaj, Spa & Wellness" kategorisi hizmet ürünleri
   için tasarlanmış görünüyor (özellikleri: Süre, Kişi Sayısı, Masaj Tipi).
   Talebimiz: Kozmetik & Kişisel Bakım > Cilt Bakım > Vücut Bakımı > Nemlendiriciler

 - 8684869609141  LIFTELLE Göğüs ve Dekolte Bakım Kremi
   Talebimiz: Kozmetik & Kişisel Bakım > Cilt Bakım > Yüz Bakımı > Yüz Kremi

{CIZGI}
4) HAVUZDAKİ ÜRÜNLERİN MARKASI

Katalogda karşılığı bulunmayan aşağıdaki 6 ürünü yeni ürün olarak gönderdik.
Marka ekleme talebimiz henüz sonuçlanmadığı için bu kayıtlar, zorunlu alan olan
marka bilgisinde "No Brand" (ID 20031592) ile oluşturuldu.

{liste(d['havuz'])}

Marka talebimiz onaylandığında bu 6 kaydın markasının da "L'CARLIE" olarak
güncellenmesini rica ederiz.

{CIZGI}

Ürün adı, açıklama, görsel ve ürün özelliği güncelleme taleplerimizi panel
üzerinden ilettik; onay sürecinde desteğinizi rica ederiz.

Gerekli görmeniz hâlinde marka tescil belgemizi, GS1 barkod kayıt belgemizi ve
ürün bilgilendirme dosyalarımızı iletebiliriz.

Saygılarımızla,
LEMOS Medikal Sağlık ve İş Güvenliği İnşaat Gıda Turizm Sanayi ve Ticaret A.Ş.
Satıcı ID: 22204
"""

yol = "/opt/lcarlie/idefix-hazirlik/DESTEK-TALEBI.txt"
open(yol, "w", encoding="utf-8").write(metin)
print(f"yazildi: {yol} ({len(metin)} karakter, {metin.count(chr(10))+1} satir)")
