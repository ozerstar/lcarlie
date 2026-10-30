"""Ekip listesi: kim, ne işe bakar, bu veriye bakınca ne diyor.

NEDEN VAR
Panelde 28 satır vardı: 8 ajans rolü + 20 uzman. Hiçbirinin adı Türkçe
değildi, görevi yazmıyordu ve ne düşündüğü görünmüyordu. Sahip 20.09.2026'da
"kimin ne dediğini, nasıl düşündüğünü görmek istiyorum" dedi.

Uzmanlar aslında rakamlı, alana özgü ifadeler üretiyordu -- ama İngilizce
("Sales bounded context: 37 orders...") ve panele hiç taşınmıyordu.

NE YAPAR
Her ekip üyesi için: Türkçe ad, tek cümlelik görev, okuduğu veri, ve o
veriye bakınca söylediği ŞEY. Sıfır model çağrısı -- hepsi sayımdır.

NE UYDURMAZ
Verisi olmayan üye "veriden konuşamam" der ve sebebini söyler. Altı üyenin
hiç veri kaynağı yok (pazar/rakip istihbaratı, araştırma, kırmızı takım,
strateji, genel müdür); bunlar ya dış araştırma ya da başkalarının
bulgusunu girdi alır. Onlara sahte bir cümle yazdırmak, paneli dolu
göstermek için yalan söylemek olurdu.

ÖLÇÜM PENCERESİ TUZAĞI
Satış ifadesi yalnız `olcumde` satırlarını sayarsa 0 çıkar (ölçüm 1 Ekim'de
başlıyor) ve "satış yok" gibi okunur. Aynı hata konuşma cevaplarında da
vardı ve düzeltildi. Burada da gerçek toplam verilir, çekince ayrıca yazılır.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import department_activation

# --- durumlar
SPEAKS = "KONUŞTU"          # veriye bakti, bir sey soyledi
NO_DATA = "VERİ YOK"        # kaynagi okunamadi
NEEDS_RESEARCH = "ARAŞTIRMA GEREKİR"   # dis kaynak olmadan konusamaz
NEEDS_INPUT = "GİRDİ BEKLER"           # baskalarinin bulgusunu girdi alir
# 🔴 "VERİ YOK" ile "İŞLEV YOK" AYRI DURUMLAR — birlestirilmeleri panele yalan
# soyletiyordu. Olculdu (22.09.2026): tasarim ekibinin okudugu
# `tasarim_sablonlari` sorgusu 93 SATIR donuyor, ama 21 uye "VERİ YOK"
# raporluyordu. Veri oradaydi; eksik olan, o satirlara bakinca ne soyleyecegini
# tanimlayan SPEAKERS islevi idi.
#
# Ikisi ayni etikete sikistirilinca "veri gelmiyor" sanilip kaynak aranir --
# oysa yazilmasi gereken sey koddur. Ayni tuzagin baska adlari:
# "bulamadi != bakamadi", "soramadim != veri yok".
ISLEV_YOK = "İŞLEV YAZILMADI"          # veri okunuyor, konusma islevi yok
ISLEM_HATASI = "İŞLEM HATASI"


@dataclass(frozen=True)
class Member:
    key: str
    name: str
    job: str
    reads: tuple[str, ...] = ()
    kind: str = "specialist"
    mode: str = "data"      # data | research | synthesis


# 20 uzman + 8 ajans rolu. Ad ve gorev Turkce; "reads" gercekten okudugu
# Company Memory sorgulari.
ROSTER: tuple[Member, ...] = (
    # --- 22.09.2026: WEB departmani ---------------------------------------
    # Sahip: "web site developer ve web site yapicisi ekle; bunlar siteyi 7/24
    # kontrol edip urun sayfalari yapacak, satis ve reklam odakli."
    # 🔴 Her uye KENDI okudugu kaynaktan konusur; sayfa uretimi ayri bir
    # zincirdir (Velo + HtmlComponent), bu uyeler onu OLCER, uretmez.
    Member("web_gelistirici", "Web Geliştirici",
           "Hangi ürünün satış sayfası var, hangisi eksik — sayfa kapsamasını "
           "okur.",
           ("urun_seo", "urun_karti", "sayfa_olcum"), kind="specialist"),
    Member("sayfa_donusum", "Sayfa Dönüşüm Uzmanı",
           "Sayfaya gelen ile satın alan arasındaki farkı okur.",
           ("ecommerce_funnel", "urun_karti"), kind="specialist"),
    Member("site_izleme", "Site İzleme Sorumlusu",
           "Sitenin ve bağlı kaynakların sağlığını okur; bozulan uç var mı.",
           ("system", "provenance"), kind="specialist"),
    # --- 22.09.2026: SEO departmani kuruldu ------------------------------
    # Kadrosuzdu cunku okuyacagi kaynak yoktu: veritabaninda "seo" gecen tek
    # bir sutun bile yoktu. Veri Wix'te duruyordu ve hic okunmuyordu.
    Member("seo_icerik", "SEO İçerik Uzmanı",
           "Ürün başlık ve açıklamalarının arama görünürlüğü açısından "
           "tanımlı olup olmadığını okur.",
           ("urun_seo",), kind="specialist"),
    Member("seo_anahtar", "Anahtar Kelime Uzmanı",
           "Hangi ürüne hangi anahtar kelime atanmış, tekrar eden ya da "
           "boş kalan var mı.",
           ("urun_seo",), kind="specialist"),
    Member("seo_teknik", "Teknik SEO Uzmanı",
           "Adres (slug) ve paylaşım etiketlerinin ürün adıyla tutarlılığını "
           "okur.",
           ("urun_seo", "urun_alan_karsilastirma"), kind="specialist"),
    # --- 22.09.2026: TEKNOLOJI / SECURITY / QUALITY / RETENTION ---------
    # Sahip: "security gibi diger basit islere bakan ekipleri de aktif hale
    # getir ve repolari gelistiren de bir ekip kur."
    Member("arac_envanteri_uzmani", "Araç Envanteri Uzmanı",
           "Şirkette hangi dış yazılım koşuyor, hangisi çalışmıyor — "
           "kurulu olmakla çalışmak ayrı şeydir.",
           reads=("arac_envanteri",), kind="specialist"),
    Member("arac_arastirmacisi", "Araç Araştırmacısı",
           "Kurulu araçların alternatifi araştırıldı mı, hangisi uzun "
           "süredir bakılmadı.",
           reads=("arac_envanteri", "capabilities"), kind="specialist"),
    Member("surum_takipcisi", "Sürüm ve Bağımlılık Takipçisi",
           "Araçların sürümünü ve lisansını okur; lisansı olmayan araç "
           "şirkette kullanılamaz.",
           reads=("arac_envanteri",), kind="specialist"),

    Member("erisim_denetcisi", "Erişim ve Yetki Denetçisi",
           "Sistemin dışarıya ne yazabildiğini okur: hangi işlem açık, "
           "hangisi kapalı.",
           reads=("action_contract", "capabilities"), kind="specialist"),
    Member("baglanti_denetcisi", "Bağlantı ve Kimlik Denetçisi",
           "Hangi dış kaynağın bağlantısı açık, hangisi kopuk — kopuk "
           "bağlantı eski veri demektir.",
           reads=("provenance", "system"), kind="specialist"),

    Member("sikayet_kok_neden", "Şikâyet Kök Neden Uzmanı",
           "Müşteri şikâyetlerini tekrar eden konuya göre okur.",
           reads=("customer_voice", "crm_unanswered"), kind="specialist"),
    Member("tekrar_satin_alma", "Tekrar Satın Alma Uzmanı",
           "Kaç müşteri ikinci kez aldı — tek seferlik alıcı ile geri "
           "gelen alıcıyı ayırır.",
           reads=("crm_customers", "sales_orders"), kind="specialist"),
    # --- 22.09.2026: Kirmizi Takim / Mevzuat / Is Gelistirme buyutuldu ---
    # Hepsi o gune kadar HIC OKUNMAYAN kaynaklara baglandi.
    Member("karar_denetcisi", "Karar Sonuç Denetçisi",
           "Geçmiş kararların sonucunu okur: öneri onaylandı mı, kanıt "
           "yeterli miydi, red team ne dedi.",
           reads=("decision_outcomes", "learning_loop"), kind="specialist"),
    Member("veri_guven_denetcisi", "Veri Güvenilirlik Denetçisi",
           "Rakamın arkasındaki kaynağı okur: bağlantı açık mı, veri ne "
           "kadar taze, hangi kapı geçti.",
           reads=("data_quality", "provenance"), kind="specialist"),
    Member("oneri_denetcisi", "Öneri Takip Denetçisi",
           "Sistemin kendi önerilerini okur: kaç öneri açıldı, kaçı "
           "karara bağlandı, kaçı bekliyor.",
           reads=("own_proposals", "agenda"), kind="specialist"),
    Member("model_denetcisi", "Model Başarı Denetçisi",
           "Hangi modelin kararı tuttu, hangisi tutmadı — başarı oranıyla.",
           reads=("learning_loop", "capabilities"), kind="specialist"),

    Member("alan_tutarlilik", "Platform Tutarlılık Denetçisi",
           "Aynı ürünün Wix ve Trendyol'daki alanlarını karşılaştırır: ad, "
           "açıklama, fiyat tutuyor mu.",
           reads=("urun_alan_karsilastirma",), kind="specialist"),
    Member("iddia_envanteri", "İddia Envanteri Uzmanı",
           "Ürün metinlerindeki iddiaları sayar ve hangi üründe hangi "
           "ifadenin geçtiğini söyler.",
           reads=("urun_bilgi", "urun_alan_karsilastirma"), kind="specialist"),
    Member("yetki_denetcisi", "Yetki ve Sınır Denetçisi",
           "Sistemin hangi işlemi yapmaya yetkili olduğunu okur: öneri mi "
           "verebiliyor, uygulayabiliyor mu.",
           reads=("action_contract",), kind="specialist"),

    Member("kanal_kapsama", "Kanal Kapsama Uzmanı",
           "Hangi ürün hangi kanalda var, hangisinde hiç yok.",
           reads=("urun_alan_karsilastirma", "platform_fiyat_matrisi"),
           kind="specialist"),
    Member("firsat_takibi", "Fırsat Takip Uzmanı",
           "Gündemdeki açık işleri iş fırsatı açısından okur: hangisi "
           "beklerse para kaybettirir.",
           reads=("agenda", "decision_outcomes"), kind="specialist"),
    Member("pazaryeri_uzmani", "Pazaryeri Uzmanı",
           "Pazaryeri fiyat ve komisyon matrisini okur: hangi kanalda marj "
           "kalıyor, hangisinde kalmıyor.",
           reads=("platform_fiyat_matrisi", "urun_karti"), kind="specialist"),
    # --- veriden konusanlar
    Member("ecommerce_sales", "Satış Analisti",
           "Siparişleri ve kalemleri okur: kaç adet satıldı, ne kadar ciro oldu.",
           ("sales_orders", "sales_items")),
    Member("product_portfolio", "Ürün ve Portföy Uzmanı",
           "Ürün kârlılığını, fiyatları ve huniyi okur: hangi ürün para kazandırıyor.",
           ("ecommerce_profitability", "ecommerce_price", "ecommerce_funnel")),
    Member("meta_performance", "Meta Reklam Analisti",
           "Reklam harcaması, gösterim ve tıklamayı okur: reklamın ölçülen maliyeti.",
           ("advertising_performance", "advertising_spend")),
    Member("creative_intelligence", "Kreatif İstihbarat",
           "Reklam kayıtlarından hangi kreatifin tuttuğunu okur.",
           ("advertising_performance",)),
    Member("social_media", "Sosyal Medya Uzmanı",
           "Kanal performansını reklam verisinden okur; organik tarafta "
           "günlük paketin onay/yayın durumunu izler.",
           ("advertising_performance", "ig_gunluk_paket")),
    Member("crm_customer", "Müşteri İlişkileri Uzmanı",
           "Cevapsız mesajları ve bekleme sürelerini okur.",
           ("crm_customers", "crm_unanswered", "open_work")),
    Member("field_b2b_sales", "Kurumsal Satış Uzmanı",
           "Aynı sipariş verisini kurumsal kanal açısından okur.",
           ("sales_orders", "sales_items")),
    Member("operations", "Operasyon Uzmanı",
           "Kargo, gönderi ve açık işleri okur.",
           ("operations_shipments", "open_work")),
    Member("regulatory_quality", "Mevzuat ve Kalite Uzmanı",
           "Karar özetinden mevzuat riskini okur.",
           ("decision_summary",)),
    Member("data_measurement", "Ölçüm ve Veri Uzmanı",
           "Ölçümün kendisi güvenilir mi, ona bakar.",
           ("advertising_performance", "advertising_spend")),
    Member("growth", "Büyüme Uzmanı",
           "Karar özetinden büyüme sinyalini okur.",
           ("decision_summary",)),
    Member("ai_prompt_engineering", "AI ve Motor Sorumlusu",
           "Hangi işin hangi model kademesinde çalıştığını denetler; riskine göre yanlış kademedekini bildirir.",
           ("capability_state", "model_kademe")),
    # 🔴 20.09.2026: bu iki uye YAPISAL OLARAK SESSIZDI. Ikisi de 'financial'
    # adli bir sorgu okuyordu ve o sorgu izin listesinde HIC YOKTU; ustelik
    # ai_reader'in mart.ekonomi_gunluk ve mart.nakit_gunluk uzerinde hicbir
    # yetkisi de yoktu. Kadroda gorunup veriden tek cumle kuramiyorlardi.
    # Sorgular eklendi, yetki verildi, ikisine ayri okuma yazildi -- cunku
    # isleri ayri: biri birim ekonomiye, digeri kaydin tutarliligina bakar.
    Member("finance", "Finans Uzmanı",
           "Günlük birim ekonomiyi okur: net ciro, katkı ve reklam sonrası kâr.",
           ("financial",)),
    Member("accounting_control", "Muhasebe Kontrol",
           "Kaydın tutarlılığına bakar: tahsil edilmemiş tutar, maliyet kalitesi, hesap kapsaması.",
           ("financial_cash",)),
    # --- kreatif ve marka (20.09.2026, sahip talebiyle buyutuldu)
    # 🔴 EKIP BUYUTMENIN SARTI VERI. Her yeni uye BASKA bir gorunume,
    #    baska bir soruyla bakar; ayni veriye ikinci bir ad koymak "farkli
    #    fikir" uretmez, ayni cumleyi iki kere soyletir.
    Member("creative_decision", "Kreatif Karar Uzmanı",
           "Reklam bazında kararı okur: hangisi izlenecek, hangisi yüksek dikkat "
           "aldığı halde satışı doğrulanmamış, hangisi yetersiz örneklem.",
           ("creative_decisions",)),
    Member("creative_hypothesis", "Kreatif Hipotez Uzmanı",
           "Açık hipotezleri ve her birinin nasıl yanlışlanacağını okur.",
           ("creative_hypotheses",)),
    # ══════════════════════════════════════════════════════════════
    # MARKA DEPARTMANI (22.09.2026'da büyütüldü)
    # Sahip: "brand ekibine büyük görev var, iş tanımlarını büyüt ve
    # aktif hale getir." Aktif olmak = veriye bakıp bir şey söyleyebilmek.
    # ══════════════════════════════════════════════════════════════
    Member("marka_kimlik", "Marka Kimlik Sorumlusu",
           "Şablon kütüğündeki marka kurallarını okur: hangi şablon logo, "
           "renk ve tipografi kuralını taşıyor, hangisinde kural yazılmamış.",
           ("tasarim_sablonlari", "tasarim_isleri")),
    Member("marka_mimarisi", "Marka Mimarisi Uzmanı",
           "Ürün kartını okur: seriler ve alt markalar (Babyline) nasıl "
           "ayrışıyor, hangi ürün hangi çatı altında duruyor.",
           ("urun_karti", "urun_bilgi")),
    Member("marka_deneyimi", "Marka Deneyimi Uzmanı",
           "Üretilen işleri ve gönderileri okur: müşteri markayla nerede "
           "temas ediyor — raf, kutu, kargo, sosyal.",
           ("tasarim_isleri", "operations_shipments", "tasarim_sablonlari")),
    Member("marka_sagligi", "Marka Sağlığı Analisti",
           "İçerik performansını ve kreatif kapsamını okur: marka hangi "
           "mesajla görülüyor, hangi mesaj hiç denenmemiş.",
           ("content_performance", "creative_coverage")),

    # ══════════════════════════════════════════════════════════════
    # HALKLA İLİŞKİLER (PR) — 22.09.2026'da KURULDU, önceden yoktu
    # ══════════════════════════════════════════════════════════════
    Member("halkla_iliskiler_muduru", "Halkla İlişkiler Müdürü",
           "Günlük dış bülteni ve içerik performansını okur: sektörde ne "
           "konuşuluyor, bizim hangi mesajımız karşılık buluyor.",
           ("gunluk_brief", "content_performance", "basin_bahsi")),
    Member("basin_iliskileri", "Basın İlişkileri Uzmanı",
           "Dış haberleri ve pazar araştırmasını okur: hangi gelişme bizim "
           "için haber değeri taşıyor, kime hangi açıyla anlatılır.",
           ("gunluk_brief", "market_research", "basin_bahsi")),
    Member("kriz_iletisimi", "Kriz İletişimi Sorumlusu",
           "Cevapsız mesajları ve karar özetini okur: hangi konu büyümeden "
           "önce cevaplanmalı, hangi mevzuat riski kamuya yansıyabilir.",
           ("crm_unanswered", "decision_summary")),
    Member("itibar_izleme", "İtibar ve Şikâyet İzleme",
           "Müşteri dilini ve cevapsızları okur: tekrar eden şikâyet hangisi, "
           "hangi cümle sık kuruluyor.",
           ("customer_voice", "crm_unanswered", "basin_bahsi")),
    Member("isbirligi_sorumlusu", "İş Birliği ve Influencer Sorumlusu",
           "Kreatif kapsamı ve içerik performansını okur: hangi iş birliği "
           "biçimi denendi, hangisi ölçülmedi.",
           ("creative_coverage", "content_performance")),
    Member("kurumsal_editor", "Kurumsal İçerik Editörü",
           "Üretilen işleri ve ürün bilgisini okur: kurumsal metinlerde "
           "hangi ürün bilgisi kullanılmış, kaynağı var mı.",
           ("tasarim_isleri", "urun_bilgi", "tasarim_sablonlari")),

    # ══════════════════════════════════════════════════════════════
    # YAYIN DEPARTMANI — katalog ve KİTAP (22.09.2026, sahip talebi)
    # "katalog ve kitap için hukuk birimi, editörler ve grafik
    #  tasarımcılar çok fazla çalışmaları lazım"
    #
    # 🔴 Katalog ile kitap AYRI editörlük ister: katalog ürün verisini
    # dizer, kitap metin yazar. Mevzuat riskleri de ayrı.
    # ══════════════════════════════════════════════════════════════
    Member("katalog_editoru", "Katalog Editörü",
           "Katalog şablonlarını ve ürün bilgisini okur: hangi sayfa hangi "
           "alanı istiyor, o alanın onaylı karşılığı var mı.",
           ("tasarim_sablonlari", "urun_bilgi", "tasarim_isleri")),
    Member("kitap_editoru", "Kitap Editörü",
           "Kitap şablonlarını okur: bölüm yapısı, künye ve kaynakça "
           "sayfası eksik mi, hangi bölüm yazılmamış.",
           ("tasarim_sablonlari", "tasarim_isleri")),
    Member("yayin_hukuk", "Yayın Hukuk ve Mevzuat Denetçisi",
           "Karar özetini ve ürün bilgisini okur: yayına girecek metinde "
           "hangi ifade iddiaya dönüşür, hangisi belge ister.",
           ("decision_summary", "urun_bilgi")),
    Member("kaynakca_sorumlusu", "Kaynakça ve Doğrulama Sorumlusu",
           "Pazar araştırmasını ve ürün bilgisini okur: kitapta yazılan "
           "genel bilginin kaynağı var mı, hangisi kaynaksız.",
           ("market_research", "urun_bilgi")),
    Member("dizgi_baski", "Dizgi ve Baskı Sorumlusu",
           "Şablon kütüğünü okur: hangi iş hangi ölçü ve dpi ile basılacak, "
           "hangisi Canva'ya sığmıyor ve harici motor istiyor.",
           ("tasarim_sablonlari", "tasarim_isleri")),

    # ══════════════════════════════════════════════════════════════
    # TASARIM DEPARTMANI (22.09.2026)
    # Sahip: "burası ayrı departman: editörü var, grafik tasarımcısı,
    # metacısı, her şeyi olan departman burası."
    #
    # 🔴 Her üyenin `reads` alanı GERÇEKTEN okuduğu sorgudur. Kaynağı
    # olmayan üye panelde "girdi bekler" der; uydurma cümle kurmaz.
    # ══════════════════════════════════════════════════════════════

    # ── Yönetim
    Member("tasarim_direktoru", "Tasarım Direktörü",
           "Tasarım defterini okur: ne üretildi, kaçı onay bekliyor, "
           "kaçı reddedildi ve hangi gerekçeyle.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("produksiyon_muduru", "Kreatif Prodüksiyon Müdürü",
           "İş akışının darboğazını okur: onay kuyruğunda kaç iş bekliyor, "
           "hangi iş türü hiç üretilemiyor.",
           ("tasarim_isleri", "tasarim_sablonlari")),

    # ── Üretim
    Member("sablon_sorumlusu", "Şablon Sorumlusu",
           "Kütüğü okur: hangi iş türünün şablonu var, hangisi yok. "
           "Şablonsuz istek üretilemez, eksik olanı söyler.",
           ("tasarim_sablonlari", "tasarim_isleri")),
    Member("grafik_tasarimci", "Grafik Tasarımcı",
           "Üretilen işlerin hangi şablon ve yerleşimle çıktığını okur; "
           "oran uyarısı almış olanları ayırır.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("dizgi_uzmani", "Dizgi ve Tipografi Uzmanı",
           "Şablona giden metinlerin uzunluğunu okur: hangi başlık "
           "çerçeveye sığmayacak kadar uzun.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("varlik_sorumlusu", "Görsel Varlık Sorumlusu",
           "Hangi ürün görseli hangi işte kullanıldı, çerçeve oranına "
           "uyuyor mu okur.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("kesim_uzmani", "Ürün Kesim ve Rötuş Uzmanı",
           "Ürün kesimlerinin ölçüsünü okur: hangi kesim hangi çerçeveye "
           "uygun, hangisi yeniden çekilmeli.",
           ("tasarim_sablonlari", "tasarim_isleri")),
    Member("video_editoru", "Video Editörü",
           "Videoya dönecek kreatifleri okur: hangi tasarım Reels/Story "
           "ölçüsünde üretilmiş; günlük paketin çekilecek reels/story'lerini izler.",
           ("tasarim_isleri", "tasarim_sablonlari", "ig_gunluk_paket")),

    # ── Marka ve uyum
    Member("marka_muhafizi", "Marka Muhafızı",
           "Mevzuat kapısının bulgularını okur: hangi ifade kesildi, "
           "hangi iş bu yüzden hiç üretilmedi.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("tasarim_metin_yazari", "Kreatif Metin Yazarı",
           "Şablona giden başlık, alt başlık ve sloganları okur: hangi "
           "mesaj kaç kez kullanıldı, tekrar var mı.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("tasarim_mevzuat", "Tasarım Mevzuat Denetçisi",
           "BLOCKED ile VERIFY bulgularını ayırır: hangisi kesin yasak, "
           "hangisi belge ile kullanılabilir.",
           ("tasarim_isleri", "tasarim_sablonlari")),

    # ── Kanal ve ölçüm
    Member("meta_kreatif", "Meta Reklam Kreatifçisi",
           "Reklam kayıtlarını okur: üretilen hangi kreatif biçimi ve "
           "hangi CTA daha çok link tıklaması getiriyor.",
           ("kreatif_performans", "tasarim_isleri")),
    Member("sosyal_editor", "Sosyal Medya Editörü",
           "Format uyumunu okur: feed, kare ve story ölçülerinden "
           "hangileri üretilmiş, hangisi eksik; günlük paketin biçimlerini izler.",
           ("tasarim_isleri", "tasarim_sablonlari", "ig_gunluk_paket")),
    Member("baski_uzmani", "Baskı ve Katalog Uzmanı",
           "Baskıya giden işleri okur: katalog, afiş, raf etiketi — ölçü "
           "ve oran uyarısı almış olanları ayırır.",
           ("tasarim_isleri", "tasarim_sablonlari")),
    Member("tasarim_performans", "Kreatif Performans Analisti",
           "Üretilen tasarımla reklam performansını eşler: hangi tasarım "
           "yayına girdi, ne getirdi.",
           ("tasarim_isleri", "kreatif_performans", "tasarim_sablonlari")),

    Member("creative_copy", "Başlık ve CTA Analisti",
           "Kreatif metnini performansla birlikte okur: hangi CTA ve hangi biçim "
           "daha çok link tıklaması getiriyor.",
           ("kreatif_performans",)),
    Member("creative_fatigue", "Kreatif Yorgunluk Analisti",
           "Frekansı okur: aynı kişi reklamı kaç kez görüyor, hangi kreatif yoruldu.",
           ("kreatif_performans",)),
    Member("brand_voice", "Müşteri Dili Uzmanı",
           "Müşterinin kendi sorduğu konuları okur: neyi soruyor, neyi hiç sormuyor.",
           ("customer_voice",)),
    Member("brand_positioning", "Konumlandırma Uzmanı",
           "Soru dağılımını fiyat gerçeğiyle birlikte okur: marka neyle anılıyor.",
           ("customer_voice", "ecommerce_price")),
    # Organik icerik (20.09.2026). Ucu de AYNI tabloya bakar ama UC AYRI
    # soruyla: ne siklikta yayinliyoruz / ne kadar karsilik goruyor / hangi
    # bicimde uretiyoruz. Ayni cumleyi uc kez soyletmemek icin sorular ayrildi.
    Member("content_cadence", "İçerik Ritmi Analisti",
           "Yayın ritmini ve metin alışkanlığını okur: ayda kaç gönderi, "
           "ne uzunlukta metin, kaç etiket, reklam ibaresi var mı; günlük "
           "paketten kaçının yayına çıktığını izler.",
           ("content_performance", "ig_gunluk_paket")),
    Member("social_engagement", "Sosyal Etkileşim Analisti",
           "Gönderi başına beğeni ve yorumu okur: hangi biçim karşılık görüyor.",
           ("content_performance",)),
    Member("art_format", "Görsel Format Analisti",
           "Üretim biçimini okur: reels mi, sabit görsel mi, hangisi ağır basıyor.",
           ("content_performance",)),
    # 20.09.2026, sahip talebiyle: "kreatif tarafini guclendir; marka
    # stratejisti ve is gelistirme uzmani onemli."
    Member("creative_coverage", "Kreatif Kapsama Analisti",
           "Hangi ürünün reklamı var, hangisinin hiç yok — ve hangi reklam "
           "hiçbir ürüne bağlanamıyor.",
           ("creative_coverage", "ecommerce_price")),
    Member("brand_strategy", "Marka Stratejisti",
           "Ne söylediğimizi ne sorulduğuyla karşılaştırır: mesajımız talebin "
           "neresine denk geliyor.",
           ("customer_voice", "content_performance")),
    Member("bizdev", "İş Geliştirme Uzmanı",
           "Kanal kapsamasını okur: kaç platform açık, kaç ürün-kanal yuvası "
           "boş, açılsa komisyon ve marj ne olur.",
           ("platform_fiyat_matrisi",)),
    # 🔴 NEDEN EKLENDI (20.09.2026): COMPETITOR_INT'in iki uyesi de arastirma
    #    modunda, yani hic sirket verisi okumuyor. Sonuc olculdu: rakip
    #    fiyatlari elimize gecti ama mudur "VIREON'un nerede durduguna dair
    #    sirket verisi yok" dedi -- KARSILASTIRAMADI. Rakip istihbarati,
    #    kendi fiyatini bilmeden yarim kalir.
    Member("price_position", "Fiyat Konumu Analisti",
           "Kendi fiyatlarımızı okur ki rakip iddialarıyla karşılaştırılabilsin.",
           ("ecommerce_price",)),
    Member("market_findings", "Pazar Bulgu Uzmanı",
           "Kayda geçmiş pazar bulgularını kaynağı ve tarihiyle okur.",
           ("market_research",)),
    # --- dis arastirma gerektirenler
    Member("market_intelligence", "Pazar İstihbaratı",
           "Pazarın dışarıdaki halini araştırır; şirket verisinden konuşamaz.",
           (), mode="research"),
    Member("competitor_intelligence", "Rakip İstihbaratı",
           "Rakiplerin hamlelerini dışarıdan araştırır.", (), mode="research"),
    Member("research", "Araştırmacı",
           "İnternette kaynak arar, bulduğunu tarih ve türüyle getirir.",
           (), mode="research"),
    # --- baskalarinin bulgusunu girdi alanlar
    Member("red_team", "Kırmızı Takım",
           "Diğerlerinin bulgusuna itiraz eder; kendi verisi yoktur.",
           (), mode="synthesis"),
    Member("strategy", "Strateji",
           "Bulguları karar seçeneğine çevirir.", (), mode="synthesis"),
    Member("managing_director", "Genel Müdür (sentez)",
           "Hepsini tek özete indirir ve çelişkiyi işaretler.",
           (), mode="synthesis"),
    # 🔴 21.09.2026'da EKLENDİ. Kadroda işbölümünü planlayan kimse yoktu;
    # bu yüzden hangi departmanın neyi araştıracağı KODDA sabitti ve
    # 45 departmanın 39'u hiç araştırma yapmıyordu. Bu rol kapsamı
    # veriden okur ve planı yazar -- plan artık koda değil, karara bağlı.
    Member("is_planlama", "İş Planlama Müdürü",
           "Hangi birimin neyi, hangi sıklıkta araştıracağını planlar; "
           "kapsama boşluğunu ölçer.",
           ("departments", "creative_coverage", "market_research",
            "evidence_readiness"),
           mode="data"),
    # --- ajans rolleri (uretim tarafi)
    Member("CREATIVE_DIRECTOR", "Kreatif Direktör",
           "Kampanyanın açısını kurar, konseptleri belirler.",
           kind="agency", mode="synthesis"),
    Member("COPYWRITER", "Metin Yazarı",
           "Başlık ve reklam gövde metnini yazar.", kind="agency", mode="synthesis"),
    Member("META_PERFORMANCE", "Meta Performans (ajans)",
           "Kampanyanın reklam tabanını hesaplar.", kind="agency", mode="synthesis"),
    Member("CREATIVE_INTELLIGENCE", "Kreatif İstihbarat (ajans)",
           "Test planını ve deney matrisini kurar.", kind="agency", mode="synthesis"),
    Member("COMPETITOR_CREATIVE", "Rakip Kreatif",
           "Rakip reklamlarına bakılması gerektiğini işaretler.",
           kind="agency", mode="research"),
    Member("SOCIAL_CONTENT", "Sosyal İçerik",
           "Haftalık gönderi planını kurar.", kind="agency", mode="synthesis"),
    Member("CRO_SPECIALIST", "Dönüşüm Uzmanı",
           "Açılış sayfası önerilerini çıkarır.", kind="agency", mode="synthesis"),
    Member("GROWTH_STRATEGIST", "Büyüme Stratejisti",
           "Problem ve fırsatları listeler.", kind="agency", mode="synthesis"),
    Member("musteri_hizmetleri", "Müşteri Hizmetleri Takipçisi",
           "Yanıtsız görüşmeleri ve ürün bilgi kapsamını izler; mesaj göndermez.",
           ("crm_unanswered", "urun_bilgi")),
    Member("musteri_istihbarati", "Müşteri İçgörü Uzmanı",
           "Anonim konu özetlerinden müşteri beklentilerini izler.",
           ("customer_voice",)),
    Member("deney_izleme", "Deney Hazırlık Uzmanı",
           "Hipotezlerin ölçüm ve yanlışlama planını denetler.",
           ("creative_hypotheses",)),
    Member("karar_hafizasi", "Karar Hafızası Uzmanı",
           "Öneri, insan kararı ve öğrenme kayıtlarının kapsamını izler.",
           ("own_proposals", "decision_outcomes", "learning_loop")),
    # 30.10.2026 sahip: "basina uzman ver". Gunluk paketi (1 urun, 5 icerik)
    # inceleyen uzman; departmanin sorumlusu. Yayin YAPMAZ, onay sahibindir.
    Member("ig_icerik_direktoru", "Instagram İçerik Direktörü",
           "Günlük paketin başında durur: 5 içeriği kanca gücü, tekrar, "
           "mevzuat ve çekilebilirlik açısından inceler; yayın yapmaz.",
           ("ig_gunluk_paket",)),
    Member("instagram_olcum", "Instagram İçerik Ölçüm Uzmanı",
           "Organik gönderi kayıtlarını ölçüm sınırlarıyla izler; yayın yapmaz.",
           ("content_performance",)),
    Member("stok_kapsama", "Stok Kapsama Denetçisi",
           "Wix stok alanının kapsamasını izler; depo envanteri iddia etmez.",
           ("urun_bilgi",)),
    Member("video_brief", "Video Brief Analisti",
           "Video içerik kayıtlarından brief girdisi çıkarır; UGC üretmez.",
           ("content_performance",)),
    Member("yeni_urun_on_arastirma", "Yeni Ürün Ön Araştırmacısı",
           "Müşteri konuları, mevcut ürün ve pazar bulgularından ön fikir üretir.",
           ("customer_voice", "urun_karti", "market_research")),
)

BY_KEY = {m.key: m for m in ROSTER}


# --------------------------------------------------------- uye -> departman
# 🔴 AYRI SOZLUK, Member'a alan EKLENMEDI. 41 tanimi tek tek degistirmek
#    hem gurultulu hem hataya acik; eslemeyi tek yerde tutmak eksigi de
#    gorunur kilar (bkz. eslenmeyen_uyeler). Kodlar core.departman.kod ile
#    ayni olmak zorunda -- panoda departman basligi oradan geliyor.
UYE_DEPARTMAN: dict[str, str] = {
    "web_gelistirici": "WEB",
    "sayfa_donusum": "WEB",
    "site_izleme": "WEB",
    "seo_icerik": "SEO",
    "seo_anahtar": "SEO",
    "seo_teknik": "SEO",
    "arac_envanteri_uzmani": "TEKNOLOJI",
    "arac_arastirmacisi": "TEKNOLOJI",
    "surum_takipcisi": "TEKNOLOJI",
    "erisim_denetcisi": "SECURITY",
    "baglanti_denetcisi": "SECURITY",
    "sikayet_kok_neden": "QUALITY",
    "tekrar_satin_alma": "RETENTION",
    "karar_denetcisi": "RED_TEAM",
    "veri_guven_denetcisi": "RED_TEAM",
    "oneri_denetcisi": "RED_TEAM",
    "model_denetcisi": "RED_TEAM",
    "alan_tutarlilik": "REGULATORY",
    "iddia_envanteri": "REGULATORY",
    "yetki_denetcisi": "REGULATORY",
    # 🔴 22.09.2026: BIZDEV -> MARKETPLACE. Ikisi de pazaryeri rolu;
    # MARKETPLACE departmani bos dururken is BIZDEV altinda yapiliyordu.
    # Kadro uydurulmadi, var olan uyeler kendi adlarinin oldugu yere
    # tasindi. BIZDEV bosalmiyor: firsat_takibi ve bizdev kaliyor.
    "kanal_kapsama": "MARKETPLACE",
    "firsat_takibi": "BIZDEV",
    "pazaryeri_uzmani": "MARKETPLACE",
    # --- 22.09.2026: departmansiz 30 uye baglandi -------------------------
    # 🔴 `eslenmeyen_uyeler()` kendi aciklamasinda "Bos donmeli; test bunu
    # bekcilik eder" diyor -- ama 30 donuyordu. TASARIM/MARKA/PR/YAYIN
    # ekipleri kadroya eklenmis, departman eslemesi yapilmamisti.
    #
    # Departmansiz uye yalnizca panelde susan bir isim degil: `_ekip_sor()`
    # departman kodundan kadroyu buluyor, dolayisiyla o uyelere HESAP
    # SORULAMIYOR ve bilgi istenemiyor. Sahip 22.09.2026: "hepsinin kendi
    # mudurleri var, ben onlarla konusurum."
    "tasarim_direktoru": "TASARIM",
    "produksiyon_muduru": "TASARIM",
    "sablon_sorumlusu": "TASARIM",
    "grafik_tasarimci": "TASARIM",
    "dizgi_uzmani": "TASARIM",
    "varlik_sorumlusu": "TASARIM",
    "kesim_uzmani": "TASARIM",
    "video_editoru": "TASARIM",
    "marka_muhafizi": "TASARIM",
    "tasarim_metin_yazari": "TASARIM",
    "tasarim_mevzuat": "TASARIM",
    "meta_kreatif": "TASARIM",
    "sosyal_editor": "TASARIM",
    "baski_uzmani": "TASARIM",
    "tasarim_performans": "TASARIM",
    "dizgi_baski": "TASARIM",

    "marka_kimlik": "BRAND",
    "marka_mimarisi": "BRAND",
    "marka_deneyimi": "BRAND",
    "marka_sagligi": "BRAND",

    "halkla_iliskiler_muduru": "PR",
    "basin_iliskileri": "PR",
    "kriz_iletisimi": "PR",
    "itibar_izleme": "PR",
    "isbirligi_sorumlusu": "PR",

    "kurumsal_editor": "YAYIN",
    "katalog_editoru": "YAYIN",
    "kitap_editoru": "YAYIN",
    "yayin_hukuk": "YAYIN",
    "kaynakca_sorumlusu": "YAYIN",
    # ticari
    "ecommerce_sales": "ECOM",
    "product_portfolio": "PRODUCT",
    "field_b2b_sales": "B2B",
    "bizdev": "BIZDEV",
    "operations": "FULFILLMENT",
    # finans
    "finance": "FINANCE",
    "accounting_control": "FINANCE",
    # veri / olcum
    "data_measurement": "DATA_BI",
    "research": "DATA_BI",
    # reklam
    "meta_performance": "META_MEDIA",
    "creative_fatigue": "META_MEDIA",
    "META_PERFORMANCE": "META_MEDIA",
    # kreatif
    "creative_intelligence": "CREATIVE_STRAT",
    "creative_decision": "CREATIVE_STRAT",
    "creative_hypothesis": "CREATIVE_STRAT",
    "creative_coverage": "CREATIVE_STRAT",
    "CREATIVE_DIRECTOR": "CREATIVE_STRAT",
    "CREATIVE_INTELLIGENCE": "CREATIVE_STRAT",
    "creative_copy": "COPY",
    "COPYWRITER": "COPY",
    "art_format": "ART",
    # marka
    "brand_voice": "BRAND",
    "brand_positioning": "BRAND",
    "brand_strategy": "BRAND",
    # icerik / sosyal
    "content_cadence": "CONTENT",
    "social_media": "SOCIAL",
    "social_engagement": "SOCIAL",
    "SOCIAL_CONTENT": "SOCIAL",
    # musteri
    "crm_customer": "CRM",
    # istihbarat
    "market_intelligence": "MARKET_INT",
    "market_findings": "MARKET_INT",
    "competitor_intelligence": "COMPETITOR_INT",
    "price_position": "COMPETITOR_INT",
    "COMPETITOR_CREATIVE": "COMPETITOR_INT",
    # yonetisim
    "regulatory_quality": "REGULATORY",
    "red_team": "RED_TEAM",
    # platform
    "ai_prompt_engineering": "AI_OPS",
    # donusum
    "CRO_SPECIALIST": "CRO",
    # yurutme
    "growth": "EXEC",
    "strategy": "EXEC",
    "managing_director": "EXEC",
    "is_planlama": "EXEC",
    "GROWTH_STRATEGIST": "EXEC",
    "musteri_hizmetleri": "CS",
    "musteri_istihbarati": "CUSTOMER_INT",
    "deney_izleme": "EXPERIMENT",
    "karar_hafizasi": "DECISION_MEM",
    "instagram_olcum": "INSTAGRAM",
    "ig_icerik_direktoru": "INSTAGRAM",
    "stok_kapsama": "INVENTORY",
    "video_brief": "UGC",
    "yeni_urun_on_arastirma": "RND",
}


def eslenmeyen_uyeler() -> tuple[str, ...]:
    """Departmani olmayan uyeler. Bos donmeli; test bunu bekcilik eder."""
    return tuple(m.key for m in ROSTER if m.key not in UYE_DEPARTMAN)


# --------------------------------------------------------------------------
# DEPARTMAN SORUMLUSU
# --------------------------------------------------------------------------
# 🔴 Sahip 22.09.2026: "hepsinin kendi mudurleri var, ben onlarla konusurum.
# Hesap sorarim veya bilgi isterim. Bu konusanlara da zaten moderatorluk
# yapacak olan bu mudurler."
#
# `_ekip_sor()` departmanin TUM kadrosunu kanit olarak topluyor; bu harita
# o cevabin KIMIN agzindan verildigini soyler. Sorumlusu tanimlanmamis
# departman, muhatabi olmayan departmandir.
DEPARTMAN_SORUMLUSU: dict[str, str] = {
    # --- 22.09.2026: sahip onayiyla atandi ------------------------------
    "WEB": "web_gelistirici",
    "SEO": "seo_icerik",
    "TEKNOLOJI": "arac_envanteri_uzmani",
    "SECURITY": "erisim_denetcisi",
    "QUALITY": "sikayet_kok_neden",
    "RETENTION": "tekrar_satin_alma",
    "COMPETITOR_INT": "price_position",
    "META_MEDIA": "meta_performance",
    "SOCIAL": "social_media",
    "COPY": "creative_copy",
    "DATA_BI": "data_measurement",
    "FINANCE": "finance",
    "MARKET_INT": "market_findings",
    "AI_OPS": "ai_prompt_engineering",
    "ART": "art_format",
    "B2B": "field_b2b_sales",
    "CONTENT": "content_cadence",
    "CRM": "crm_customer",
    "ECOM": "ecommerce_sales",
    "FULFILLMENT": "operations",
    "PRODUCT": "product_portfolio",
    "CRO": "CRO_SPECIALIST",
    "RED_TEAM": "karar_denetcisi",
    "REGULATORY": "alan_tutarlilik",
    "BIZDEV": "pazaryeri_uzmani",
    "TASARIM": "tasarim_direktoru",
    "BRAND": "marka_kimlik",
    "PR": "halkla_iliskiler_muduru",
    "YAYIN": "kurumsal_editor",
    "CREATIVE_STRAT": "CREATIVE_DIRECTOR",
    "EXEC": "managing_director",
    "CS": "musteri_hizmetleri",
    "CUSTOMER_INT": "musteri_istihbarati",
    "EXPERIMENT": "deney_izleme",
    "DECISION_MEM": "karar_hafizasi",
    # 30.10.2026 sahip karari: departmanin basina icerik direktoru.
    "INSTAGRAM": "ig_icerik_direktoru",
    "INVENTORY": "stok_kapsama",
    "UGC": "video_brief",
    "RND": "yeni_urun_on_arastirma",
}


def departman_sorumlusu(kod: str) -> Member | None:
    """Departmanin muhatabi. Tanimli degilse None -- uydurulmaz."""
    anahtar = DEPARTMAN_SORUMLUSU.get(kod)
    if not anahtar:
        return None
    return BY_KEY.get(anahtar)


def departman_uyeleri() -> dict[str, tuple[Member, ...]]:
    """Departman kodu -> o departmanin uyeleri."""
    kova: dict[str, list[Member]] = {}
    for m in ROSTER:
        kod = UYE_DEPARTMAN.get(m.key)
        if kod:
            kova.setdefault(kod, []).append(m)
    return {k: tuple(v) for k, v in kova.items()}


# ------------------------------------------------------------- görüş üretimi
def _num(row: dict, *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _top(rows, key, value_key, reverse=True):
    """Bir alana göre en yüksek/düşük satır. Boşsa None."""
    adaylar = [r for r in rows if r.get(key) and _num(r, value_key)]
    if not adaylar:
        return None
    return sorted(adaylar, key=lambda r: _num(r, value_key), reverse=reverse)[0]


def _group_sum(rows, key, value_key):
    out: dict[str, float] = {}
    for row in rows:
        ad = str(row.get(key) or "").strip()
        if ad:
            out[ad] = out.get(ad, 0.0) + _num(row, value_key)
    return out


def _ads30(rows):
    return [r for r in rows.get("advertising_performance", []) if r.get("pencere") == 30]


def _say_sales(rows: dict[str, list]) -> str:
    """Satış Analisti: hacim, ciro ve en çok satan ürün."""
    orders, items = rows.get("sales_orders", []), rows.get("sales_items", [])
    adet = sum(int(r.get("adet") or 0) for r in items)
    ciro = sum(_num(r, "satir_ciro_net") for r in items)
    olcumde = sum(1 for r in orders if r.get("olcumde"))
    metin = (f"{len(orders)} siparişte {adet} adet ürün, {ciro:,.0f} TL net ciro.")
    urun_ciro = _group_sum(items, "urun_adi", "satir_ciro_net")
    if urun_ciro:
        en_iyi = max(urun_ciro.items(), key=lambda kv: kv[1])
        pay = en_iyi[1] / ciro * 100 if ciro else 0
        metin += (f" En çok ciro {en_iyi[0].split('(')[0].strip()[:28]}: "
                  f"{en_iyi[1]:,.0f} TL (cironun %{pay:.0f}'i).")
    # Sifir gostermek yerine sebebini soyle.
    if orders and olcumde == 0:
        metin += " Hiçbiri ölçüm penceresinde değil; satışlar yine de gerçek."
    return metin


def _say_b2b(rows: dict[str, list]) -> str:
    """Kurumsal Satış: hangi kanal satıyor."""
    orders = rows.get("sales_orders", [])
    if not orders:
        return "Sipariş kaydı yok."
    kanal = _group_sum(orders, "kanal", "ciro_beyan_edilmis_net")
    if not kanal:
        sayim: dict[str, int] = {}
        for r in orders:
            ad = str(r.get("kanal") or "bilinmiyor")
            sayim[ad] = sayim.get(ad, 0) + 1
        dagilim = ", ".join(f"{k}: {v}" for k, v in
                            sorted(sayim.items(), key=lambda kv: -kv[1])[:4])
        return f"{len(orders)} siparişin kanal dağılımı — {dagilim}."
    sirali = sorted(kanal.items(), key=lambda kv: -kv[1])
    toplam = sum(kanal.values()) or 1
    return ("Kanal bazında ciro — " + ", ".join(
        f"{ad}: {tutar:,.0f} TL (%{tutar / toplam * 100:.0f})"
        for ad, tutar in sirali[:4]) + ".")


def _say_ads(rows: dict[str, list]) -> str:
    """Meta Reklam Analisti: maliyet verimliliği."""
    perf = _ads30(rows)
    if not perf:
        return "30 günlük pencerede reklam kaydı yok."
    harcama = sum(_num(r, "harcama") for r in perf)
    gosterim = sum(int(r.get("gosterim") or 0) for r in perf)
    tiklama = sum(int(r.get("tiklama") or 0) for r in perf)
    aktif = sum(1 for r in perf if str(r.get("etkin_durum") or "").upper().startswith("ACTIVE"))
    cpc = harcama / tiklama if tiklama else 0
    cpm = harcama / gosterim * 1000 if gosterim else 0
    return (f"30 günde {harcama:,.0f} TL harcandı. Tıklama başı {cpc:,.2f} TL, "
            f"bin gösterim başı {cpm:,.2f} TL. {aktif}/{len(perf)} kayıt aktif.")


def _say_creative(rows: dict[str, list]) -> str:
    """Kreatif İstihbarat: hangi reklam metni tutuyor."""
    perf = [r for r in _ads30(rows) if r.get("ad_adi")]
    if not perf:
        return "Reklam bazında kayıt yok; hangi kreatifin tuttuğu ölçülemiyor."
    sirali = sorted(perf, key=lambda r: _num(r, "ctr_yuzde"), reverse=True)
    iyi, kotu = sirali[0], sirali[-1]
    return (f"{len(perf)} reklam karşılaştırıldı. En yüksek TO "
            f"'{str(iyi.get('ad_adi'))[:30]}' ile %{_num(iyi, 'ctr_yuzde'):.2f}; "
            f"en düşük '{str(kotu.get('ad_adi'))[:30]}' ile "
            f"%{_num(kotu, 'ctr_yuzde'):.2f}.")


def _say_social(rows: dict[str, list]) -> str:
    """Sosyal Medya: hangi kampanya/kitle erişiyor."""
    perf = _ads30(rows)
    if not perf:
        return "Kampanya bazında kayıt yok."
    erisim = _group_sum(perf, "kampanya_adi", "erisim")
    if not erisim:
        return f"{len(perf)} kayıt var ama kampanya adı taşımıyor."
    sirali = sorted(erisim.items(), key=lambda kv: -kv[1])
    toplam = sum(erisim.values()) or 1
    return (f"{len(sirali)} kampanya, toplam {toplam:,.0f} erişim. En geniş: "
            + ", ".join(f"{ad[:26]} ({v / toplam * 100:.0f}%)"
                        for ad, v in sirali[:3]) + ".")


def _say_measurement(rows: dict[str, list]) -> str:
    """Ölçüm ve Veri: ölçümün kendisi güvenilir mi."""
    perf = _ads30(rows)
    if not perf:
        return "Ölçülecek reklam kaydı yok."
    teyitli = sum(1 for r in perf if r.get("commercial_confirmation") == "CONFIRMED")
    meta_iddia = sum(_num(r, "meta_gelir_iddiasi") for r in perf)
    metin = (f"{len(perf)} kaydın {teyitli}'inde ticari doğrulama var "
             f"(%{teyitli / len(perf) * 100:.0f}).")
    if meta_iddia:
        metin += (f" Meta {meta_iddia:,.0f} TL gelir iddia ediyor; doğrulama "
                  f"olmadan bu rakam ciro sayılamaz.")
    else:
        metin += " Meta tarafında gelir iddiası da yok."
    return metin


def _say_crm(rows: dict[str, list]) -> str:
    """Müşteri İlişkileri: cevapsız ve bekleme."""
    cevapsiz = rows.get("crm_unanswered", [])
    musteri = rows.get("crm_customers", [])
    if not cevapsiz:
        return f"{len(musteri)} müşteri kaydı var, cevapsız konuşma görünmüyor."
    en_uzun = max((_num(r, "bekleme_saat") for r in cevapsiz), default=0)
    gun = en_uzun / 24
    return (f"{len(cevapsiz)} cevapsız müşteri konuşması var; en uzunu "
            f"{gun:.0f} gündür bekliyor. Toplam müşteri kaydı {len(musteri)}.")


def _say_products(rows: dict[str, list]) -> str:
    """Ürün ve Portföy: marj ve maliyet kapsaması."""
    kar = rows.get("ecommerce_profitability", [])
    fiyat = rows.get("ecommerce_price", [])
    eksik = sum(1 for r in kar if _num(r, "kapsama_yuzde") < 100)
    metin = f"Katalogda {len(fiyat)} ürün; {len(kar)} üründe kârlılık hesaplanabiliyor."
    if kar:
        # Karlilik gorunumunde URUN ADI YOK: `kalem` kalem SAYISIDIR ve kimlik
        # UUID. Ad fiyat listesinden entity_id ile eslestirilir -- olculdu:
        # 20 kaydin 19'u esleser. Eslesmeyen icin ad UYDURULMAZ.
        adlar = {}
        for satir in rows.get("ecommerce_price", []):
            adlar[str(satir.get("entity_id"))] = str(satir.get("urun_adi") or "")
        en_iyi = max(kar, key=lambda r: _num(r, "brut_marj"), default=None)
        if en_iyi is not None and _num(en_iyi, "brut_marj"):
            ad = adlar.get(str(en_iyi.get("entity_id"))) or "(adı eşleşmedi)"
            metin += (f" En yüksek brüt marj {ad.split('(')[0].strip()[:28]}: "
                      f"{_num(en_iyi, 'brut_marj'):,.0f} TL.")
    if eksik:
        metin += (f" {eksik} üründe maliyet kapsaması eksik; o ürünlerin marjı "
                  f"olduğundan iyi görünüyor.")
    return metin


def _say_operations(rows: dict[str, list]) -> str:
    """Operasyon: taşıyıcı, transit, alarm, kapıda ödeme."""
    gonderi = rows.get("operations_shipments", [])
    acik = rows.get("open_work", [])
    if not gonderi:
        return f"Gönderi kaydı yok; {len(acik)} açık iş var."
    alarmli = sum(1 for r in gonderi if r.get("alarm"))
    kapida = sum(1 for r in gonderi if r.get("cod_var"))
    transitler = [_num(r, "transit_gun") for r in gonderi if _num(r, "transit_gun")]
    ort = sum(transitler) / len(transitler) if transitler else 0
    tasiyici = _group_sum(gonderi, "tasiyici", "kargo_ucreti")
    metin = f"{len(gonderi)} gönderi; ortalama transit {ort:.1f} gün."
    if alarmli:
        metin += f" {alarmli} gönderide alarm var."
    if kapida:
        metin += f" {kapida} gönderi kapıda ödeme."
    if tasiyici:
        ad, ucret = max(tasiyici.items(), key=lambda kv: kv[1])
        metin += f" En çok kargo ücreti {ad[:20]}: {ucret:,.0f} TL."
    if acik:
        metin += f" {len(acik)} açık iş."
    return metin


def _say_decisions(rows: dict[str, list]) -> str:
    kararlar = rows.get("decision_summary", [])
    if not kararlar:
        return "Karar özeti boş."
    return f"{len(kararlar)} karar kaydı okunabiliyor."


def _say_capability(rows: dict[str, list]) -> str:
    """AI ve Motor Sorumlusu: hangi iş hangi modelde, doğru yerde mi.

    🔴 BU CÜMLE BİR ÖLÇÜMDEN DOĞDU (22.09.2026). Altı çağrı yerinin
    dördü kodda `escalate=True` istiyordu ama zincir her zaman en küçük
    modelden başlayıp ilk cevapta durduğu için istek hiç karşılanmadı:
    defterde 79 gemini çağrısına karşılık 1 claude vardı. Yani müşteriye
    giden metinler en küçük modelle üretiliyordu ve panelde hiçbir yerde
    görünmüyordu. Bu rol artık onu görünür kılıyor.
    """
    durum = rows.get("capability_state", [])
    atama = rows.get("model_kademe", [])
    if not atama:
        return ("Kademe kaydı okunamadı — hangi işin hangi modelle "
                "çalıştığı doğrulanamıyor."
                + (f" {len(durum)} yetenek kaydı okunabiliyor." if durum else ""))

    muhakeme = [a for a in atama if str(a.get("kademe")) == "muhakeme"]
    hizli = [a for a in atama if str(a.get("kademe")) == "hizli"]
    # 🔴 ASIL DENETİM: müşteriye giden ya da karar besleyen bir iş hızlı
    # kademede duruyorsa bu bir bulgudur, sessiz geçilemez.
    yanlis = [a for a in atama
              if str(a.get("kademe")) == "hizli"
              and str(a.get("risk")) in ("MUSTERIYE", "KARARA")]

    metin = (f"{len(atama)} iş kademeye bağlı: {len(muhakeme)} muhakeme, "
             f"{len(hizli)} hızlı.")
    if muhakeme:
        metin += (" Muhakemede olanlar: "
                  + ", ".join(sorted(str(a.get("is_anahtari")) for a in muhakeme)[:6])
                  + ".")
    if yanlis:
        metin += (f" 🔴 {len(yanlis)} iş riskine göre YANLIŞ kademede: "
                  + ", ".join(sorted(str(a.get("is_anahtari")) for a in yanlis))
                  + " — müşteriye giden ya da karar besleyen iş hızlı "
                    "kademede çalışmamalı.")
    else:
        metin += " Riskine göre yanlış kademede iş yok."
    if not durum:
        metin += " Yetenek durumu okunamadı."
    return metin


# Hangi uye hangi cumleyi kurar. Ayni veriyi okuyan iki uye ayni cumleyi
# kurar -- bu bir kusur degil, gercegin kendisi: ikisi de ayni gorunume
# bakiyor. Panel bunu gizlemez.
def _say_creative_decision(rows: dict[str, list]) -> str:
    """Kreatif Karar: etikete gore sayim. CTR'yi satis SAYMAZ."""
    k = rows.get("creative_decisions", [])
    if not k:
        return "Kreatif karar görünümü boş."
    etiket: dict[str, int] = {}
    for r in k:
        etiket[str(r.get("etiket") or "?")] = etiket.get(str(r.get("etiket") or "?"), 0) + 1
    dogrulanan = sum(1 for r in k
                     if str(r.get("commercial_confirmation") or "") not in ("", "NOT_AVAILABLE"))
    sirali = sorted(etiket.items(), key=lambda kv: -kv[1])
    metin = (f"{len(k)} reklam kararı: "
             + "; ".join(f"{ad} {n}" for ad, n in sirali[:4]) + ".")
    # 🔴 Bu cumle kaldirilamaz: yuksek CTR'yi "kazanan reklam" diye okumak
    #    bu projede acikca yasak, cunku atif kurulamiyor.
    metin += (f" Ticari doğrulaması olan reklam: {dogrulanan}/{len(k)}. "
              f"Doğrulama yoksa CTR yalnız dikkat ölçer, satış değil.")
    return metin


def _say_creative_hypothesis(rows: dict[str, list]) -> str:
    """Kreatif Hipotez: acik hipotez ve nasil yanlislanacagi."""
    h = rows.get("creative_hypotheses", [])
    if not h:
        return "Açık kreatif hipotezi yok."
    yanlislanabilir = sum(1 for r in h if str(r.get("yanlislama") or "").strip())
    metin = f"{len(h)} açık kreatif hipotezi var; {yanlislanabilir}'inde yanlışlama koşulu yazılı."
    ilk = h[0]
    konu = str(ilk.get("hipotez") or "")[:90]
    if konu:
        metin += f" En üstteki: “{konu}”."
    if yanlislanabilir < len(h):
        metin += (f" {len(h) - yanlislanabilir} hipotezin yanlışlama koşulu yok — "
                  f"çürütülemeyen hipotez sınanamaz.")
    return metin


def _say_creative_copy(rows: dict[str, list]) -> str:
    """Baslik ve CTA: CTA ve bicim kirilimi. Farkli CTA'lar KIYASLANAMAZ."""
    k = [r for r in rows.get("kreatif_performans", []) if r.get("yeterli_ornek")]
    if not k:
        return "Değerlendirilebilir kreatif yok (hepsi örneklem altında)."
    def kirilim(alan: str) -> list[tuple[str, float, int]]:
        kova: dict[str, list[float]] = {}
        for r in k:
            ad = str(r.get(alan) or "(yok)")
            kova.setdefault(ad, []).append(_num(r, "link_ctr"))
        return sorted(((ad, sum(v) / len(v), len(v)) for ad, v in kova.items()),
                      key=lambda t: -t[1])
    cta = kirilim("cta")[:3]
    bicim = kirilim("bicim")[:2]
    metin = (f"{len(k)} ölçülebilir kreatif. CTA'ya göre link CTR — "
             + "; ".join(f"{ad} %{o:.1f} ({n})" for ad, o, n in cta) + ".")
    if bicim:
        metin += " Biçim — " + "; ".join(f"{ad} %{o:.1f}" for ad, o, _ in bicim) + "."
    metin += (" Dikkat: farklı CTA'lar farklı şey satın alır; profil görüntüleme "
              "tıklaması ucuzdur ama satış değildir, bu oranlar doğrudan kıyaslanamaz.")
    return metin


def _say_creative_fatigue(rows: dict[str, list]) -> str:
    """Kreatif Yorgunluk: frekans. Ayni kisi kac kez gordu."""
    k = rows.get("kreatif_performans", [])
    if not k:
        return "Frekans okunabilecek kreatif yok."
    yorgun = [r for r in k if _num(r, "en_yuksek_frekans") >= 2.5]
    en_yuksek = max((_num(r, "en_yuksek_frekans") for r in k), default=0.0)
    metin = f"{len(k)} kreatifin {len(yorgun)}'inde frekans 2,5'in üstünde."
    if en_yuksek:
        metin += f" En yüksek frekans {en_yuksek:.1f}."
    if yorgun:
        metin += (" Aynı kişi reklamı tekrar tekrar görüyor; yeni açı üretilmezse "
                  "harcama aynı kitleye biner.")
    else:
        metin += " Yorgunluk sinyali yok."
    return metin


def _say_brand_voice(rows: dict[str, list]) -> str:
    """Musteri Dili: musterinin KENDI sordugu konular. Marka ne ile aniliyor."""
    s = rows.get("customer_voice", [])
    if not s:
        return "Müşteri soru dağılımı okunamıyor."
    sirali = sorted(s, key=lambda r: -_num(r, "konusma_yuzde"))
    ust = sirali[:3]
    dip = [r for r in sirali if _num(r, "konusma_yuzde") <= 1]
    metin = ("Müşterinin sorduğu konular — "
             + "; ".join(f"{r.get('konu')} %{_num(r,'konusma_yuzde'):.0f}" for r in ust) + ".")
    if dip:
        metin += (" Neredeyse hiç sorulmayanlar: "
                  + ", ".join(str(r.get("konu")) for r in dip[:3]) + ".")
    metin += (" Sorulmayan konu, ilgi olmadığını değil, o konunun müşteriye hiç "
              "ulaşmadığını da gösterebilir.")
    return metin


def _say_brand_positioning(rows: dict[str, list]) -> str:
    """Konumlandirma: soru dagilimi ile fiyat gercegini YAN YANA koyar."""
    s = rows.get("customer_voice", [])
    f = rows.get("ecommerce_price", [])
    if not s:
        return "Konumlandırma için soru dağılımı okunamıyor."
    fiyat = next((r for r in s if str(r.get("konu")) == "FIYAT"), None)
    icerik = next((r for r in s if str(r.get("konu")) == "ICERIK"), None)
    fayda = next((r for r in s if str(r.get("konu")) == "ETKI_FAYDA"), None)
    parcalar = []
    if fiyat is not None:
        parcalar.append(f"fiyat %{_num(fiyat,'konusma_yuzde'):.0f}")
    if icerik is not None:
        parcalar.append(f"içerik %{_num(icerik,'konusma_yuzde'):.0f}")
    if fayda is not None:
        parcalar.append(f"fayda %{_num(fayda,'konusma_yuzde'):.0f}")
    metin = f"Katalogda {len(f)} ürün var. Konuşmaların " + ", ".join(parcalar) + " ile açılıyor."
    if fiyat is not None and fayda is not None:
        fo, fa = _num(fiyat, "konusma_yuzde"), _num(fayda, "konusma_yuzde")
        if fa and fo / fa >= 3:
            metin += (f" Fiyat sorusu fayda sorusunun {fo/fa:.0f} katı: marka şu an "
                      f"ürünün ne yaptığıyla değil, ne kadar olduğuyla anılıyor.")
    return metin


def _say_creative_coverage(rows: dict[str, list]) -> str:
    """Kreatif Kapsama: HIC reklami olmayan urunu gorunur kilar."""
    e = rows.get("creative_coverage", [])
    katalog = rows.get("ecommerce_price", [])
    if not e:
        return "Reklam–ürün eşleşmesi okunamıyor."
    urunler = {str(r.get("urun_id")) for r in e if r.get("urun_id")}
    baglanamayan = sum(1 for r in e if str(r.get("kaynak") or "") == "YOK"
                       or not r.get("urun_id"))
    metin = f"{len(e)} reklamın {len(urunler)} ürüne bağı kurulmuş."
    if katalog:
        reklamsiz = len(katalog) - len(urunler)
        metin += (f" Katalogda {len(katalog)} ürün var; "
                  f"{max(reklamsiz,0)} ürünün hiç reklamı yok.")
    if baglanamayan:
        # 🔴 Bu sayi gizlenmez: bagi kurulamayan reklamin harcamasi hicbir
        #    urune yazilamaz, yani urun bazli maliyet OLDUGUNDAN DUSUK gorunur.
        metin += (f" {baglanamayan} reklam hiçbir ürüne bağlanamıyor; "
                  f"onların harcaması ürün bazında görünmez.")
    return metin


def _say_brand_strategy(rows: dict[str, list]) -> str:
    """Marka Stratejisti: NE SOYLUYORUZ ile NE SORULUYOR'u yan yana koyar."""
    soru = rows.get("customer_voice", [])
    icerik = rows.get("content_performance", [])
    if not soru:
        return "Talep tarafı okunamıyor; mesaj–talep karşılaştırması yapılamaz."
    talep = sorted(soru, key=lambda r: -_num(r, "konusma_yuzde"))
    ust_talep = [str(r.get("konu")) for r in talep[:2]]
    metin = f"Talebin ilk iki konusu: {', '.join(ust_talep)}."
    if icerik:
        # Mesaj tarafi: kendi metnimizde fiyat/icerik gecen gonderi orani.
        fiyatli = sum(1 for r in icerik
                      if "fiyat" in str(r.get("icerik_basi") or "").casefold()
                      or " tl" in str(r.get("icerik_basi") or "").casefold())
        icerikli = sum(1 for r in icerik
                       if "içind" in str(r.get("icerik_basi") or "").casefold()
                       or "bileşen" in str(r.get("icerik_basi") or "").casefold())
        metin += (f" Kendi {len(icerik)} gönderimizin açılışında fiyat {fiyatli}, "
                  f"içerik {icerikli} kez geçiyor.")
        if fiyatli == 0 and "FIYAT" in ust_talep:
            metin += (" Talebin birinci konusu fiyat ama gönderilerimizin hiçbiri "
                      "fiyatla açılmıyor — mesaj talebin sorduğu yerde değil.")
    metin += (" 🔴 Bu bir ÖRTÜŞME karşılaştırmasıdır, nedensellik değil: "
              "insanlar fiyatı soruyor olabilir çünkü başka yerde bulamıyorlar.")
    return metin


def _say_bizdev(rows: dict[str, list]) -> str:
    """Is Gelistirme: kanal kapsamasi. Acik olmayan kanal = kullanilmayan raf."""
    p = rows.get("platform_fiyat_matrisi", [])
    if not p:
        return "Platform matrisi okunamıyor."
    kanallar: dict[str, dict[str, Any]] = {}
    for r in p:
        ad = str(r.get("platform_adi") or r.get("platform_kod") or "?")
        k = kanallar.setdefault(ad, {"urun": 0, "aktif": False, "yazma": 0})
        k["urun"] += 1
        if r.get("platform_aktif"):
            k["aktif"] = True
        if r.get("yazma_izni"):
            k["yazma"] += 1
    acik = [ad for ad, k in kanallar.items() if k["aktif"]]
    kapali = [ad for ad, k in kanallar.items() if not k["aktif"]]
    bos_yuva = sum(k["urun"] for ad, k in kanallar.items() if not k["aktif"])
    # 🔴 Sayiya ek getirme ("2'i / 2'si") Turkcede sayiya gore degisir ve
    #    kod icinde dogru uretmek zordur. Cumleyi eke ihtiyac birakmayacak
    #    sekilde kur: "5 kanaldan 2 tanesi acik".
    metin = (f"{len(kanallar)} kanaldan {len(acik)} tanesi açık "
             f"({', '.join(sorted(acik)) or '-'}).")
    if kapali:
        metin += (f" Kapalı: {', '.join(sorted(kapali))} — "
                  f"{bos_yuva} ürün-kanal yuvası hiç açılmamış.")
    yazan = sum(k["yazma"] for k in kanallar.values())
    if yazan == 0:
        metin += (" Hiçbir kanalda yazma izni yok: fiyat/stok bu sistemden "
                  "değiştirilemez, yalnız okunur.")
    return metin


def _ay_kova(icerik: list) -> dict[str, int]:
    kova: dict[str, int] = {}
    for r in icerik:
        gun = str(r.get("observed_at") or "")[:7]
        if gun:
            kova[gun] = kova.get(gun, 0) + 1
    return kova


def _say_content_cadence(rows: dict[str, list]) -> str:
    """Icerik Ritmi: ne siklikta yayinliyoruz, metin aliskanligi ne."""
    i = rows.get("content_performance", [])
    if not i:
        return "Organik içerik verisi okunamıyor."
    aylar = _ay_kova(i)
    ort_ay = sum(aylar.values()) / len(aylar) if aylar else 0
    uzunluk = [_num(r, "icerik_uzunluk") for r in i if _num(r, "icerik_uzunluk")]
    etiket = [_num(r, "etiket_sayisi") for r in i]
    ibaresiz = sum(1 for r in i if not r.get("reklam_ibaresi"))
    metin = (f"{len(i)} gönderi, {len(aylar)} ay: ayda ortalama {ort_ay:.1f} gönderi.")
    if uzunluk:
        metin += f" Metin ortalama {sum(uzunluk)/len(uzunluk):.0f} karakter"
    if etiket:
        metin += f", ortalama {sum(etiket)/len(etiket):.1f} etiket."
    if aylar:
        en_dusuk = min(aylar.items(), key=lambda kv: kv[1])
        metin += f" En az üretilen ay {en_dusuk[0]} ({en_dusuk[1]} gönderi)."
    # 🔴 Mevzuat izi sessiz gecilmez: reklam iceren gonderide ibare zorunlu.
    if ibaresiz:
        metin += (f" {ibaresiz} gönderide reklam/tanıtım ibaresi geçmiyor; "
                  f"reklam niteliği taşıyorlarsa ibare zorunludur.")
    return metin


def _say_social_engagement(rows: dict[str, list]) -> str:
    """Sosyal Etkilesim: begeni ve yorum. ORAN DEGIL SAYI -- erisim bilinmiyor."""
    i = rows.get("content_performance", [])
    if not i:
        return "Etkileşim okunabilecek gönderi yok."
    kova: dict[str, list[float]] = {}
    for r in i:
        kova.setdefault(str(r.get("bicim") or "?"), []).append(_num(r, "etkilesim"))
    sirali = sorted(((ad, sum(v) / len(v), len(v)) for ad, v in kova.items()),
                    key=lambda t: -t[1])
    begeni = sum(_num(r, "begeni") for r in i)
    yorum = sum(_num(r, "yorum") for r in i)
    metin = ("Biçim başına ortalama etkileşim — "
             + "; ".join(f"{ad} {o:.1f} ({n} gönderi)" for ad, o, n in sirali) + ".")
    metin += f" Toplam {begeni:,.0f} beğeni, {yorum:,.0f} yorum."
    if begeni and yorum / max(begeni, 1) < 0.02:
        metin += (" Yorum/beğeni oranı %2'nin altında: içerik beğeni topluyor "
                  "ama konuşma başlatmıyor.")
    # 🔴 Bu uyari kaldirilamaz.
    metin += (" Erişim verisi alınamıyor (izin yok), bu yüzden bunlar SAYIDIR; "
              "etkileşim oranı hesaplanamaz.")
    return metin


def _say_art_format(rows: dict[str, list]) -> str:
    """Gorsel Format: ne uretiyoruz. Uretim karmasi, karsiligi degil."""
    i = rows.get("content_performance", [])
    if not i:
        return "Format okunabilecek gönderi yok."
    bicim: dict[str, int] = {}
    tur: dict[str, int] = {}
    for r in i:
        bicim[str(r.get("bicim") or "?")] = bicim.get(str(r.get("bicim") or "?"), 0) + 1
        tur[str(r.get("tur") or "?")] = tur.get(str(r.get("tur") or "?"), 0) + 1
    toplam = len(i)
    sirali = sorted(bicim.items(), key=lambda kv: -kv[1])
    metin = ("Üretim karması — "
             + "; ".join(f"{ad} {n} (%{100*n/toplam:.0f})" for ad, n in sirali) + ".")
    video = sum(n for ad, n in tur.items() if ad == "VIDEO")
    if video:
        metin += f" Videolu içerik {video}/{toplam} (%{100*video/toplam:.0f})."
    yz = sum(1 for r in i if r.get("yz_beyani"))
    if yz:
        metin += (f" {yz} gönderide yapay zekâ beyanı var (%{100*yz/toplam:.0f}); "
                  f"görsel üretimin ağırlığı burada okunuyor.")
    return metin


def _say_price_position(rows: dict[str, list]) -> str:
    """Fiyat Konumu: KENDI fiyatlarimiz. Rakip iddiasiyla kiyaslanabilsin diye."""
    f = rows.get("ecommerce_price", [])
    if not f:
        return "Fiyat gerçeği okunamıyor; rakip karşılaştırması yapılamaz."
    fiyatlar = [(_num(r, "musteriye_soylenecek_fiyat") or _num(r, "wix_satis"),
                 str(r.get("urun_adi") or "")) for r in f]
    fiyatlar = [(p, ad) for p, ad in fiyatlar if p]
    if not fiyatlar:
        return f"{len(f)} üründe fiyat alanı boş; karşılaştırılacak rakam yok."
    fiyatlar.sort()
    en_dusuk, en_yuksek = fiyatlar[0], fiyatlar[-1]
    ort = sum(p for p, _ in fiyatlar) / len(fiyatlar)
    return (f"{len(fiyatlar)} üründe müşteriye söylenecek fiyat var: "
            f"en düşük {en_dusuk[0]:,.0f} TL ({en_dusuk[1].split('(')[0].strip()[:24]}), "
            f"en yüksek {en_yuksek[0]:,.0f} TL ({en_yuksek[1].split('(')[0].strip()[:24]}), "
            f"ortalama {ort:,.0f} TL. Rakip rakamlarıyla kıyaslarken hacim (ml) "
            f"farkına dikkat: aynı fiyat farklı hacimde farklı şey demektir.")


def _say_market_findings(rows: dict[str, list]) -> str:
    """Pazar Bulgu: kayitli bulgular, kaynagiyla. Kaynaksiz bulgu sayilmaz."""
    p = rows.get("market_research", [])
    if not p:
        return "Kayda geçmiş pazar bulgusu yok."
    kaynakli = sum(1 for r in p if str(r.get("kaynak") or "").strip())
    metin = f"{len(p)} pazar bulgusu kayıtlı; {kaynakli}'i kaynağıyla birlikte."
    ilk = p[0]
    bulgu = str(ilk.get("bulgu") or "")[:90]
    if bulgu:
        metin += f" En yeni: “{bulgu}”."
    if kaynakli < len(p):
        metin += f" {len(p)-kaynakli} bulgunun kaynağı yok; doğrulanana kadar iddia sayılmaz."
    return metin


def _say_finance(rows: dict[str, list]) -> str:
    """Finans: gunluk birim ekonomi. Sifir model cagrisi, hepsi sayimdir."""
    gunler = rows.get("financial", [])
    if not gunler:
        return "Ekonomi görünümü boş; birim ekonomi hesaplanamıyor."
    son = gunler[0]
    harcama = sum(_num(g, "reklam_harcamasi") for g in gunler)
    ciro = sum(_num(g, "net_ciro") for g in gunler)
    katki = sum(_num(g, "reklam_sonrasi_katki") for g in gunler)
    # 🔴 "Siparis yok" ile "olculemedi" AYRI SEYLER. ekonomi_durumu alani
    #    bunu zaten ayiriyor; kendi yorumumu ustune koymuyorum.
    harcamali_siparissiz = sum(1 for g in gunler
                               if str(g.get("ekonomi_durumu") or "") == "HARCAMA_VAR_SIPARIS_YOK")
    metin = (f"Son {len(gunler)} günde net ciro {ciro:,.0f} TL, reklam harcaması "
             f"{harcama:,.0f} TL, reklam sonrası katkı {katki:,.0f} TL.")
    if harcamali_siparissiz:
        metin += (f" {harcamali_siparissiz} günde harcama var ama sipariş yok "
                  f"(ekonomi_durumu=HARCAMA_VAR_SIPARIS_YOK).")
    tamlik = _num(son, "ekonomi_tamlik_yuzde")
    if tamlik and tamlik < 100:
        metin += (f" En son günün ekonomi tamlığı %{tamlik:,.0f}; eksik bileşen "
                  f"varken katkı olduğundan iyi görünür.")
    return metin


def _say_accounting(rows: dict[str, list]) -> str:
    """Muhasebe Kontrol: kaydin tutarliligi -- rakamin kendisi degil, guvenilirligi."""
    gunler = rows.get("financial_cash", [])
    if not gunler:
        return "Nakit görünümü boş; kayıt tutarlılığı denetlenemiyor."
    tahsil_edilmemis = sum(_num(g, "tahsil_edilmemis") for g in gunler)
    brut = sum(_num(g, "brut_ciro") for g in gunler)
    olculmus = [_num(g, "cogs_olculmus_yuzde") for g in gunler
                if _num(g, "cogs_olculmus_yuzde")]
    metin = (f"Son {len(gunler)} günde brüt ciro {brut:,.0f} TL; "
             f"tahsil edilmemiş {tahsil_edilmemis:,.0f} TL.")
    if olculmus:
        metin += f" Maliyetin ölçülmüş kısmı ortalama %{sum(olculmus)/len(olculmus):,.0f}."
    else:
        metin += " Maliyetin ölçülmüş kısmı yok; marj tahminî maliyetle hesaplanıyor."
    # Meta hesap kapsamasi: eksikse reklam harcamasi OLDUGUNDAN DUSUK gorunur,
    # yani kar OLDUGUNDAN YUKSEK. Bu sessiz gecilemez.
    kapsama = [str(g.get("meta_hesap_kapsamasi") or "") for g in gunler]
    eksik_kapsama = [k for k in kapsama if k and k != "TAM" and "1/1" not in k]
    if eksik_kapsama:
        metin += (f" Reklam hesabı kapsaması eksik ({eksik_kapsama[0]}): "
                  f"harcama olduğundan düşük, dolayısıyla kâr olduğundan yüksek görünür.")
    return metin


# --------------------------------------------------------------------------
# TASARIM / CANVA EKİBİ KONUŞMACILARI (22.09.2026)
# --------------------------------------------------------------------------
# Kadroya eklenmişlerdi ama konuşma işlevleri yazılmamıştı; panelde
# "VERİ YOK" görünüyorlardı. Her biri AYNI iki kaynağa bakar ama FARKLI
# soruyu sorar -- aksi halde 21 üye aynı cümleyi kurardı ve kadro
# kalabalıklaşırdı, zenginleşmezdi.
def _tasarim_sayilar(rows: dict[str, list]) -> dict:
    s = rows.get("tasarim_sablonlari", []) or []
    i = rows.get("tasarim_isleri", []) or []
    canvali = [r for r in s if r.get("canva_id")]
    return {
        "sablon": len(s),
        "aktif": sum(1 for r in s if r.get("aktif")),
        "canvali": len(canvali),
        "canvasiz": len(s) - len(canvali),
        "is": len(i),
        "onay_bekleyen": sum(1 for r in i if r.get("onay_bekliyor")),
        "basarisiz": sum(1 for r in i
                         if str(r.get("durum") or "").upper() == "BASARISIZ"),
        "turler": len({str(r.get("is_turu") or "") for r in s if r.get("is_turu")}),
        "isler": i,
        "sablonlar": s,
    }


def _say_sablon_sorumlusu(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    if not d["sablon"]:
        return "Şablon kütüğü boş."
    return (f"{d['sablon']} şablon kayıtlı, {d['aktif']} tanesi aktif. "
            f"🔴 Yalnız {d['canvali']} tanesinin Canva bağlantısı var; "
            f"{d['canvasiz']} şablon kâğıt üstünde tanımlı ama Canva'da "
            f"karşılığı yok — bunlardan üretim yapılamaz.")


def _say_tasarim_direktoru(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    if not d["is"]:
        return ("Hiç tasarım işi açılmamış. Şablon var, üreten yok: iş "
                "kuyruğu boş olduğu sürece ekip çalışmaz.")
    return (f"{d['is']} tasarım işi var; {d['onay_bekleyen']} tanesi onay "
            f"bekliyor, {d['basarisiz']} tanesi başarısız bitti. "
            "İş sayısı şablon sayısının çok altında — darboğaz üretimde "
            "değil, iş açmakta.")


def _say_kreatif_produksiyon(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    if not d["sablon"]:
        return "Şablon kütüğü boş; üretim planlanamaz."
    oran = (d["is"] / d["sablon"] * 100) if d["sablon"] else 0
    return (f"{d['sablon']} şablona karşılık {d['is']} iş açılmış "
            f"(%{oran:.1f}). Kapasite kullanılmıyor: üretilebilir şablon "
            f"sayısı {d['canvali']} ile sınırlı, asıl tıkanma orada.")


def _say_grafik_tasarimci(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    turler = sorted({str(r.get("is_turu") or "") for r in d["sablonlar"]
                     if r.get("is_turu")})
    if not turler:
        return "Şablon türü tanımlı değil."
    return (f"{len(turler)} farklı iş türü için şablon var "
            f"({', '.join(turler[:6])}…). Ama {d['canvasiz']} tanesi "
            "Canva'ya bağlı değil; tasarımcı bunlar için sıfırdan başlamak "
            "zorunda kalır.")


def _say_gorsel_varlik(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    olculu = [r for r in d["sablonlar"] if r.get("en") and r.get("boy")]
    if not olculu:
        return "Şablonlarda ölçü bilgisi yok."
    return (f"{len(olculu)}/{d['sablon']} şablonun en-boy ölçüsü tanımlı. "
            "Ölçüsü olmayan şablon, çıktı boyutu belirsiz olduğu için "
            "baskıya ve reklama hazır sayılmaz.")


def _say_tasarim_mevzuat(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    if not d["is"]:
        return ("Denetlenecek tasarım işi yok. Mevzuat kapısı üretimden "
                "ÖNCE çalışır; iş açılmadıkça denetim de yapılmaz.")
    return (f"{d['is']} iş üretildi ve {d['onay_bekleyen']} tanesi hâlâ onay "
            "bekliyor. Onaysız tasarım yayına giremez; bekleyen iş, "
            "üretilmiş ama kullanılamayan iştir.")


def _say_meta_reklam_kreatifci(rows: dict[str, list]) -> str:
    """🔴 OKUMADIĞI KAYNAĞI 'SIFIR' DİYE RAPORLAMA — okumadigi_kaynak.

    İlk hâli "0 tasarım şablonu ve 63 reklam kreatifi kayıtlı" diyordu.
    Oysa bu üye `tasarim_sablonlari` sorgusunu HİÇ OKUMUYOR (yalnız
    `kreatif_performans` ve `tasarim_isleri`). Sıfır, şablon olmadığı
    anlamına gelmiyordu -- bakmadığı anlamına geliyordu. Kütükte 93 şablon
    var. Bütün oturum boyunca kovaladığım tuzağın kendi kodumdaki hâli.
    """
    k = rows.get("kreatif_performans", []) or []
    isler = rows.get("tasarim_isleri", []) or []
    olculur = [r for r in k if r.get("yeterli_ornek")]
    return (f"{len(k)} reklam kreatifi kayıtlı, {len(olculur)} tanesi "
            f"ölçülebilir örnekleme sahip. Tasarım tarafında {len(isler)} iş "
            "açılmış. İkisi arasında bağ kurulmamış: hangi tasarım işinden "
            "çıkan reklamın tuttuğu bilinmiyor.")


def _say_kreatif_performans_analisti(rows: dict[str, list]) -> str:
    k = rows.get("kreatif_performans", []) or []
    d = _tasarim_sayilar(rows)
    if not k:
        return "Ölçülecek kreatif kaydı yok."
    olculur = [r for r in k if r.get("yeterli_ornek")]
    return (f"{len(k)} kreatifin {len(olculur)} tanesi ölçülebilir örnekleme "
            f"sahip. Tasarım tarafında {d['is']} iş var; ikisi eşleşmediği "
            "için 'hangi tasarım işi hangi reklam sonucunu verdi' sorusu "
            "bugün cevaplanamıyor.")


def _say_video_editoru(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    video = [r for r in d["sablonlar"]
             if "video" in str(r.get("is_turu") or "").lower()]
    return (f"{len(video)} video şablonu tanımlı, toplam {d['is']} iş "
            "açılmış. Video üretimi için şablon tek başına yetmez; "
            "kaynak çekim ve süre şartnamesi de gerekir.")


def _say_sosyal_medya_editoru(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    sosyal = [r for r in d["sablonlar"]
              if any(x in str(r.get("is_turu") or "").lower()
                     for x in ("instagram", "story", "reels", "sosyal", "post"))]
    return (f"{len(sosyal)} sosyal medya şablonu var. Açılmış iş sayısı "
            f"{d['is']}; yayın ritmi kurulabilmesi için iş kuyruğunun "
            "düzenli beslenmesi gerekiyor.")


def _say_baski_katalog(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    baski = [r for r in d["sablonlar"]
             if any(x in str(r.get("is_turu") or "").lower()
                    for x in ("afis", "katalog", "kitap", "brosur", "kart"))]
    return (f"{len(baski)} baskı/katalog şablonu tanımlı. Baskıya gitmeden "
            "önce ölçü ve Canva bağlantısı şart; şu an "
            f"{d['canvasiz']} şablonda Canva karşılığı yok.")


def _say_dizgi_baski(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    return (f"{d['sablon']} şablonun baskı hazırlığı için ölçü ve Canva "
            f"bağlantısı gerekir; {d['canvasiz']} şablonda Canva karşılığı "
            "yok. Bunlar baskıya gönderilemez.")


def _say_dizgi_uzmani(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    return (f"{d['is']} tasarım işi üretildi. Tipografi denetimi üretilmiş iş "
            "üzerinde yapılır; iş kuyruğu boş kaldıkça dizgi kalitesi de "
            "ölçülemez.")


def _say_kesim_uzmani(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    return (f"{d['sablon']} şablon tanımlı. Ürün kesim işi şablona değil "
            "kaynak çekime bağlıdır; kesilmiş görsel arşivi ayrı tutulur ve "
            "şablon kütüğünden izlenemez.")


def _say_marka_muhafizi(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    return (f"{d['is']} iş üretilmiş, {d['onay_bekleyen']} tanesi onay "
            "bekliyor. Marka çizgisi denetimi onaydan ÖNCE yapılır; "
            "bekleyen iş yığını denetimin de geciktiği anlamına gelir.")


def _say_tasarim_metin_yazari(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    alanli = [r for r in d["sablonlar"] if r.get("canva_id")]
    return (f"Metin yazılabilecek şablon sayısı {len(alanli)} "
            f"(toplam {d['sablon']}). Canva'ya bağlı olmayan şablonda metin "
            "alanı yoktur; yazılan metnin gideceği yer yok demektir.")


def _say_katalog_editoru(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    u = rows.get("urun_bilgi", []) or []
    katalog = [r for r in d["sablonlar"]
               if "katalog" in str(r.get("is_turu") or "").lower()]
    return (f"{len(u)} ürün kaydı ve {len(katalog)} katalog şablonu var. "
            "Katalog üretimi için ikisinin eşleşmesi gerekir; şu an ürün "
            "başına hangi şablonun kullanılacağı tanımlı değil.")


def _say_kitap_editoru(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    kitap = [r for r in d["sablonlar"]
             if "kitap" in str(r.get("is_turu") or "").lower()]
    return (f"{len(kitap)} kitap şablonu tanımlı, açılmış iş {d['is']}. "
            "Kitap işi uzun soluklu; şablon hazır olsa bile içerik akışı "
            "olmadan üretim başlamaz.")


def _say_kurumsal_editor(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    u = rows.get("urun_bilgi", []) or []
    return (f"{len(u)} ürün metni ve {d['is']} tasarım işi var. Kurumsal "
            "içerik ikisini birleştirir; iş kuyruğu boşken düzenlenecek "
            "çıktı da yok.")


def _say_marka_kimlik(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    return (f"{d['sablon']} şablonun {d['canvali']} tanesi Canva'da mevcut. "
            "Marka kimliğinin tutarlı uygulanabilmesi şablonun gerçekten "
            "var olmasına bağlı; şartname tek başına kimlik taşımaz.")


def _say_marka_deneyimi(rows: dict[str, list]) -> str:
    d = _tasarim_sayilar(rows)
    o = rows.get("operations_shipments", []) or []
    return (f"{d['is']} tasarım işi ve {len(o)} gönderi kaydı okunuyor. "
            "Müşterinin gördüğü deneyim ikisinin toplamı; tasarım tarafı "
            "henüz bu kadar az işle deneyimi etkileyecek hacimde değil.")


# --------------------------------------------------------------------------
# MARKA / PR / YAYIN / EXEC KONUŞMACILARI (22.09.2026)
# --------------------------------------------------------------------------
# 🔴 Sahip: "Boş konuşanı sevmem, herkes kendi alanında uzman olmak zorunda."
# Her işlev KENDİ kaynağındaki sayıyı söyler; kaynağı boşsa bunu açıkça
# söyler ve genel geçer cümle kurmaz. "Marka bilinirliğini artırmalıyız"
# gibi her şirkette doğru olan cümle, hiçbir şirkette bir şey söylemez.
def _say_marka_mimarisi(rows: dict[str, list]) -> str:
    k = rows.get("urun_karti", []) or []
    b = rows.get("urun_bilgi", []) or []
    if not k:
        return "Ürün kartı okunamadı; portföy mimarisi çıkarılamaz."
    yayinda = [r for r in k if r.get("wix_yayinda")]
    return (f"{len(k)} ürün kartı, {len(yayinda)} tanesi yayında; "
            f"{len(b)} üründe tam metin var. Marka mimarisi ürün adlarının "
            "tutarlılığına bağlı — ad değişikliği URL ve SEO'yu da etkiler, "
            "bu yüzden teknik değil ticari karardır.")


def _say_marka_sagligi(rows: dict[str, list]) -> str:
    c = rows.get("content_performance", []) or []
    k = rows.get("creative_coverage", []) or []
    if not c:
        return "İçerik performansı okunamadı; marka sağlığı ölçülemez."
    kapsanan = {str(r.get("ad_adi") or "") for r in k if r.get("ad_adi")}
    return (f"{len(c)} içerik kaydı ve {len(k)} kreatif kapsama satırı var; "
            f"reklamı olan ayrı kreatif sayısı {len(kapsanan)}. Marka sağlığı "
            "için tek başına yeterli değil: beğeni ve erişim var ama "
            "hatırlanma ve tercih ölçümü yok.")


def _say_halkla_iliskiler(rows: dict[str, list]) -> str:
    g = rows.get("gunluk_brief", []) or []
    c = rows.get("content_performance", []) or []
    if not g and not c:
        return "Gündem ve içerik verisi okunamadı; PR gündemi kurulamaz."
    return (f"{len(g)} günlük brief kaydı ve {len(c)} içerik ölçümü "
            "okunuyor. PR tarafında yayımlanmış bülten ya da basın çıktısı "
            "kaydı YOK — yani şu an ölçülecek bir PR faaliyeti bulunmuyor.")


def _say_basin_iliskileri(rows: dict[str, list]) -> str:
    g = rows.get("gunluk_brief", []) or []
    m = rows.get("market_research", []) or []
    return (f"{len(m)} pazar bulgusu ve {len(g)} gündem kaydı var. Basın "
            "ilişkisi için haber değeri taşıyan bir olay gerekir; "
            "kayıtlarda ürün lansmanı, ödül ya da ölçülmüş bir başarı "
            "bildirimi bulunmuyor.")


def _say_kriz_iletisimi(rows: dict[str, list]) -> str:
    c = rows.get("crm_unanswered", []) or []
    d = rows.get("decision_summary", []) or []
    if not c:
        return ("Cevapsız mesaj kaydı okunamadı; kriz sinyali "
                "değerlendirilemez.")
    return (f"{len(c)} cevapsız müşteri mesajı var. Kriz iletişimi için eşik "
            "tek mesaj değil, aynı konuda YIĞILMA — bugün için tekil "
            f"şikâyet düzeyinde. {len(d)} karar özeti kaydı izleniyor.")


def _say_itibar_izleme(rows: dict[str, list]) -> str:
    v = rows.get("customer_voice", []) or []
    c = rows.get("crm_unanswered", []) or []
    if not v:
        return "Müşteri sesi kaydı okunamadı; itibar izlenemez."
    return (f"{len(v)} müşteri sesi kaydı ve {len(c)} cevapsız mesaj "
            "okunuyor. Dışarıdaki itibar (yorum siteleri, sosyal medya "
            "bahsi) bu kaynaklarda YOK — itibar şu an yalnız bize "
            "yazılanlardan ölçülüyor, bu eksik bir görüntüdür.")


def _say_isbirligi_sorumlusu(rows: dict[str, list]) -> str:
    k = rows.get("creative_coverage", []) or []
    c = rows.get("content_performance", []) or []
    return (f"{len(k)} kreatif kapsama ve {len(c)} içerik kaydı var. "
            "İş birliği tarafında anlaşma, brief ya da ödeme kaydı "
            "tutulmuyor; hangi iş birliğinin ne getirdiği bugün "
            "ölçülemiyor.")


def _say_yayin_hukuk(rows: dict[str, list]) -> str:
    d = rows.get("decision_summary", []) or []
    u = rows.get("urun_bilgi", []) or []
    return (f"{len(u)} ürün metni denetim kapsamında, {len(d)} karar özeti "
            "izleniyor. Yayın öncesi hukuk denetimi metin ÜRETİLDİKTEN "
            "sonra değil, brief aşamasında yapılmalı; aksi halde çekilmiş "
            "içerik son anda çöpe gider.")


def _say_kaynakca_sorumlusu(rows: dict[str, list]) -> str:
    m = rows.get("market_research", []) or []
    u = rows.get("urun_bilgi", []) or []
    kaynakli = [r for r in m if r.get("kaynak")]
    return (f"{len(m)} pazar bulgusunun {len(kaynakli)} tanesinde kaynak "
            f"belirtilmiş. {len(u)} ürün metni doğrulama kapsamında. "
            "Kaynağı olmayan bulgu iddiadır ve yayına giremez.")


def _say_is_planlama(rows: dict[str, list]) -> str:
    dep = rows.get("departments", []) or []
    k = rows.get("creative_coverage", []) or []
    m = rows.get("market_research", []) or []
    e = rows.get("evidence_readiness", []) or []
    if not dep:
        return "Departman listesi okunamadı; planlama yapılamaz."
    calisan = [r for r in dep if str(r.get("durum") or "") == "CALISIYOR"]
    yok = [r for r in dep if str(r.get("durum") or "") == "YOK"]
    return (f"{len(dep)} departmanın {len(calisan)} tanesi çalışıyor, "
            f"{len(yok)} tanesi hiç kurulmamış. {len(m)} pazar bulgusu ve "
            f"{len(k)} kreatif kapsama kaydı var; kanıt hazırlığı "
            f"{len(e)} satır. Planlama önceliği kurulmamış departmanlarda.")


# --- Kirmizi Takim / Mevzuat / Is Gelistirme konusmacilari (22.09.2026) ----
def _say_karar_denetcisi(rows: dict[str, list]) -> str:
    k = rows.get("decision_outcomes", []) or []
    if not k:
        return "Karar kaydı okunamadı."
    bekleyen = [r for r in k if str(r.get("durum")) == "PROPOSED"]
    zayif = [r for r in k if str(r.get("kanit_kalitesi")).upper() == "LOW"]
    itiraz = [r for r in k if str(r.get("red_team_sonucu")).upper() == "CHALLENGE"]
    return (f"{len(k)} karar kaydı; {len(bekleyen)} tanesi hâlâ öneri "
            f"aşamasında. {len(zayif)} kararın kanıt kalitesi DÜŞÜK, "
            f"{len(itiraz)} tanesine kırmızı takım itiraz etmiş. "
            "Kanıtı zayıf karar, onaylanmış olsa bile güvenilir değildir.")


def _say_veri_guven_denetcisi(rows: dict[str, list]) -> str:
    q = rows.get("data_quality", []) or []
    p = rows.get("provenance", []) or []
    if not q and not p:
        return "Veri kalitesi ve kaynak kaydı okunamadı."
    gecen = [r for r in q if r.get("passed")]
    kopuk = [r for r in p
             if str(r.get("current_connection", "")).upper() != "CONNECTED"]
    metin = (f"{len(q)} veri kapısının {len(gecen)} tanesi geçti. "
             f"{len(p)} kaynak izleniyor")
    if kopuk:
        metin += f"; {len(kopuk)} tanesinin bağlantısı KOPUK"
    return metin + ". Bağlantısı kopuk kaynaktan gelen rakam eskidir."


def _say_oneri_denetcisi(rows: dict[str, list]) -> str:
    o = rows.get("own_proposals", []) or []
    g = rows.get("agenda", []) or []
    if not o:
        return f"Öneri kaydı yok; gündemde {len(g)} açık iş var."
    bekleyen = [r for r in o if not r.get("decided_at")]
    return (f"{len(o)} öneri üretilmiş, {len(bekleyen)} tanesi karara "
            f"bağlanmamış. Gündemde {len(g)} açık iş var. "
            "Karara bağlanmayan öneri, yapılmamış iş demektir.")


def _say_model_denetcisi(rows: dict[str, list]) -> str:
    l = rows.get("learning_loop", []) or []
    if not l:
        return "Model başarı kaydı okunamadı."
    sirali = sorted(l, key=lambda r: -(_num(r, "basari_orani") or 0))
    ilk = sirali[0]
    return (f"{len(l)} model/sağlayıcı izleniyor. En yüksek başarı: "
            f"{ilk.get('model') or ilk.get('provider')} "
            f"%{_num(ilk, 'basari_orani'):.0f} "
            f"({int(_num(ilk, 'karar_sayisi') or 0)} karar). "
            "Az sayıda kararla ölçülen oran güvenilir değildir.")


def _say_alan_tutarlilik(rows: dict[str, list]) -> str:
    a = rows.get("urun_alan_karsilastirma", []) or []
    if not a:
        return "Platform karşılaştırma verisi okunamadı."
    sayac: dict[str, int] = {}
    for r in a:
        d = str(r.get("durum") or "?")
        sayac[d] = sayac.get(d, 0) + 1
    farkli = sayac.get("FARKLI", 0)
    yalniz_wix = sayac.get("YALNIZ_WIX", 0)
    return (f"{len(a)} alan karşılaştırıldı: {farkli} tanesi İKİ PLATFORMDA "
            f"FARKLI, {yalniz_wix} tanesi yalnız Wix'te var. "
            "Aynı ürünün adı, açıklaması ya da fiyatı kanaldan kanala "
            "değişiyorsa müşteri hangisine bakacağını bilmez; iddia "
            "tutarlılığı da bozulur.")


def _say_iddia_envanteri(rows: dict[str, list]) -> str:
    u = rows.get("urun_bilgi", []) or []
    a = rows.get("urun_alan_karsilastirma", []) or []
    if not u:
        return "Ürün metni okunamadı; iddia envanteri çıkarılamaz."
    aciklamali = [r for r in u if str(r.get("aciklama_duz") or "").strip()]
    aciklama_farki = [r for r in a
                      if str(r.get("alan")) == "Açıklama"
                      and str(r.get("durum")) == "FARKLI"]
    return (f"{len(u)} üründen {len(aciklamali)} tanesinde metin var. "
            f"{len(aciklama_farki)} üründe açıklama iki platformda FARKLI — "
            "yani aynı ürün için iki ayrı iddia metni yayında.")


def _say_yetki_denetcisi(rows: dict[str, list]) -> str:
    c = rows.get("action_contract", []) or []
    if not c:
        return "Yetki sözleşmesi okunamadı."
    onerebilir = [r for r in c if r.get("proposal_enabled")]
    uygulayabilir = [r for r in c if r.get("execution_enabled")]
    return (f"{len(c)} işlem türü tanımlı: {len(onerebilir)} tanesinde öneri "
            f"verilebiliyor, {len(uygulayabilir)} tanesinde uygulama açık. "
            "Uygulama kapalıyken sistem dışarıya hiçbir şey yazamaz; "
            "bu bir kısıt değil, kasıtlı bir kapıdır.")


def _say_kanal_kapsama(rows: dict[str, list]) -> str:
    a = rows.get("urun_alan_karsilastirma", []) or []
    if not a:
        return "Kanal kapsama verisi okunamadı."
    # 🔴 ALAN sayılır, ÜRÜN değil. İlk hâlinde benzersiz ürün adı sayılıyordu
    # ve çıktı "36 ürünün alanı yalnız Wix'te dolu" oluyordu — 36 ürünün
    # TAMAMI öyleymiş gibi okunuyordu. Ölçülen şey ürün × alan kesişimi:
    # aynı ürünün bir alanı yalnız Wix'te dolu, başka alanı iki kanalda da
    # boş olabilir. İki farklı şeyi aynı sayıyla söylemek yanıltır.
    yalniz_wix = [r for r in a if str(r.get("durum")) == "YALNIZ_WIX"]
    yok = [r for r in a if str(r.get("durum")) == "IKISINDE_DE_YOK"]
    etkilenen = {str(r.get("urun_adi")) for r in yalniz_wix}
    return (f"{len(a)} ürün-alan kesişiminden {len(yalniz_wix)} tanesi yalnız "
            f"Wix'te dolu ({len(etkilenen)} farklı ürünü ilgilendiriyor), "
            f"{len(yok)} tanesi iki kanalda da boş. "
            "Kanalda alanı boş olan ürün orada bulunmaz.")


def _say_firsat_takibi(rows: dict[str, list]) -> str:
    g = rows.get("agenda", []) or []
    if not g:
        return "Gündem okunamadı."
    p0 = [r for r in g if str(r.get("oncelik")) == "P0"]
    p1 = [r for r in g if str(r.get("oncelik")) == "P1"]
    return (f"Gündemde {len(g)} açık iş var: {len(p0)} tanesi en yüksek, "
            f"{len(p1)} tanesi yüksek öncelikte. En yüksek öncelikli iş "
            "beklerken açılan her yeni iş, sıradaki işi de geciktirir.")


def _say_pazaryeri_uzmani(rows: dict[str, list]) -> str:
    m = rows.get("platform_fiyat_matrisi", []) or []
    if not m:
        return "Pazaryeri matrisi okunamadı."
    uyarili = [r for r in m if r.get("marj_uyari")]
    return (f"{len(m)} kanal-ürün satırı izleniyor; {len(uyarili)} tanesinde "
            "marj uyarısı var. Komisyon ve KDV düşülmeden hesaplanan marj "
            "gerçek marj değildir.")


def _basin_ozet(rows: dict[str, list]) -> dict:
    b = rows.get("basin_bahsi", []) or []
    riskli = [r for r in b if str(r.get("mevzuat_durumu")) == "RISKLI"]
    siteler = {str(r.get("kaynak_site") or "") for r in b if r.get("kaynak_site")}
    bayraklar: list[str] = []
    for r in riskli:
        for x in (r.get("mevzuat_bayragi") or []):
            if x and x not in bayraklar:
                bayraklar.append(str(x))
    return {"kayit": len(b), "riskli": len(riskli),
            "site": len(siteler), "bayrak": bayraklar}


def _say_itibar_izleme_v2(rows: dict[str, list]) -> str:
    """🔴 Onceki hali 'disaridaki itibar kaynaklarda YOK' diyordu; dogruydu
    ama sebebi arac eksikligi degil YANLIS KAYNAKTI. Google News marka
    adinin 8 varyantinda da 0 donduruyor, oysa haberler var."""
    d = _basin_ozet(rows)
    v = rows.get("customer_voice", []) or []
    if not d["kayit"]:
        return ("Basın taraması henüz çalışmadı; dış itibar için "
                f"{len(v)} müşteri sesi kaydından başka veri yok.")
    metin = (f"{d['site']} farklı sitede {d['kayit']} bahis kayıtlı. "
             f"{len(v)} müşteri sesi kaydıyla birlikte okunuyor.")
    if d["riskli"]:
        metin += (f" 🔴 {d['riskli']} bahis mevzuat kapısına takıldı "
                  f"({', '.join(d['bayrak'][:4])}). Basında çıkan ifade de "
                  "bize ait sayılabilir; ispat külfeti reklamverendedir.")
    return metin


def _say_halkla_iliskiler_v2(rows: dict[str, list]) -> str:
    d = _basin_ozet(rows)
    g = rows.get("gunluk_brief", []) or []
    if not d["kayit"]:
        return (f"{len(g)} gündem kaydı okunuyor; basın çıktısı kaydı yok. "
                "Tarama çalıştırılmadıkça PR faaliyeti ölçülemez.")
    return (f"{d['kayit']} basın bahsi, {d['site']} farklı sitede. "
            f"Bunların {d['riskli']} tanesi mevzuat açısından riskli. "
            "PR'ın ölçüsü bahis sayısı değil, bahsin ne söylediğidir.")


def _say_basin_iliskileri_v2(rows: dict[str, list]) -> str:
    d = _basin_ozet(rows)
    m = rows.get("market_research", []) or []
    if not d["kayit"]:
        return (f"{len(m)} pazar bulgusu var, basın bahsi kaydı yok.")
    return (f"{d['kayit']} bahis {d['site']} sitede yayımlanmış. "
            f"{len(m)} pazar bulgusuyla birlikte değerlendirilir. "
            "Yeni bahis için haber değeri taşıyan bir olay gerekir.")


# --- TEKNOLOJI / SECURITY / QUALITY / RETENTION konusmacilari (22.09.2026) --
def _say_arac_envanteri(rows: dict[str, list]) -> str:
    a = rows.get("arac_envanteri", []) or []
    if not a:
        return "Araç envanteri boş; hangi yazılımı koşturduğumuz yazılı değil."
    calisan = [r for r in a if r.get("calisiyor")]
    durmus = [r for r in a if r.get("kurulu") and not r.get("calisiyor")]
    metin = f"{len(a)} dış araç kayıtlı, {len(calisan)} tanesi çalışıyor."
    if durmus:
        adlar = ", ".join(str(r.get("ad")) for r in durmus[:3])
        metin += (f" 🔴 {len(durmus)} araç KURULU ama ÇALIŞMIYOR ({adlar}). "
                  "Kurulu olmak çalışmak değildir.")
    return metin


def _say_arac_arastirmacisi(rows: dict[str, list]) -> str:
    a = rows.get("arac_envanteri", []) or []
    if not a:
        return "Araç envanteri okunamadı; alternatif araştırması yapılamaz."
    bakilmamis = [r for r in a if not r.get("alternatif_bakildi")]
    return (f"{len(a)} araçtan {len(bakilmamis)} tanesinin alternatifi hiç "
            "araştırılmadı. Bir araç çalışıyor diye en iyisi olduğu "
            "anlamına gelmez; piyasada daha iyisi çıkmış olabilir.")


def _say_surum_takipcisi(rows: dict[str, list]) -> str:
    a = rows.get("arac_envanteri", []) or []
    if not a:
        return "Araç envanteri okunamadı."
    # 🔴 SAHIP KARARI 22.09.2026: "lisanssız şirkette kullanılmaz kuralını
    # kaldırıyorum. Eğer bir repo yararlı, kullanışlı ve faydalıysa
    # kullanılmalıdır." Bu yüzden lisans artık ENGEL değil, BİLGİ.
    # Kayıt amaçlı: lisansı olmayan kod hukuken varsayılan olarak "tüm
    # hakları saklı" sayılır; risk kabul edilmiş durumdadır.
    lisanssiz = [r for r in a if not str(r.get("lisans") or "").strip()]
    surumsuz = [r for r in a if not str(r.get("surum") or "").strip()]
    calismayan = [r for r in a if r.get("kurulu") and not r.get("calisiyor")]
    metin = (f"{len(a)} araç izleniyor; {len(surumsuz)} tanesinde sürüm "
             f"bilgisi, {len(lisanssiz)} tanesinde lisans bilgisi kayıtlı "
             "değil (lisans kuralı kaldırıldı — bilgi amaçlı tutuluyor).")
    if calismayan:
        metin += (f" {len(calismayan)} araç kurulu ama çalışmıyor; "
                  "sürüm takibi önce onlarda yapılmalı.")
    return metin


def _say_erisim_denetcisi(rows: dict[str, list]) -> str:
    c = rows.get("action_contract", []) or []
    if not c:
        return "Yetki sözleşmesi okunamadı; sistemin sınırı bilinmiyor."
    acik = [r for r in c if r.get("execution_enabled")]
    return (f"{len(c)} işlem türünden {len(acik)} tanesinde dışarıya yazma "
            "AÇIK. En az yetki ilkesi: kapalı olan her uç, kazara yapılacak "
            "bir değişikliğin önündeki engeldir.")


# 🔴 "CONNECTED DEĞİL" HEPSİ KOPUK DEMEK DEĞİLDİR. İlk hâlinde bu işlev
# CONNECTED olmayan her kaynağı KOPUK sayıyordu ve 12 kaynak öyle
# raporlanıyordu. Oysa aralarında:
#   PARTIAL                   -> çalışıyor ama eksik (cogs, shipment)
#   MANUAL_CONTROLLED_INPUT   -> sahip kararıyla elle giriliyor, arıza değil
#   OPTIONAL_RECONCILIATION_GAP -> kabul edilmiş boşluk
#   BLOCKED_BY_EXTERNAL_CREDENTIAL / SOURCE_NOT_CONNECTED -> GERÇEKTEN engelli
# hepsini "kopuk" demek, kabul edilmiş bir durumu arıza gibi göstermek olur;
# gerçek engelli kaynak da kalabalıkta kaybolur.
ENGELLI_DURUMLAR = ("SOURCE_NOT_CONNECTED", "BLOCKED_BY_EXTERNAL_CREDENTIAL",
                    "NONE", "UNKNOWN")


def _say_baglanti_denetcisi(rows: dict[str, list]) -> str:
    p = rows.get("provenance", []) or []
    if not p:
        return "Kaynak bağlantı kaydı okunamadı."
    def durum(r: dict) -> str:
        return str(r.get("current_connection", "")).upper()
    acik = [r for r in p if durum(r) == "CONNECTED"]
    engelli = [r for r in p if durum(r) in ENGELLI_DURUMLAR]
    kismi = [r for r in p if durum(r) == "PARTIAL"]
    kabul = [r for r in p
             if durum(r) in ("MANUAL_CONTROLLED_INPUT",
                             "OPTIONAL_RECONCILIATION_GAP")]
    metin = (f"{len(p)} kaynak: {len(acik)} tanesi tam açık, "
             f"{len(kismi)} tanesi kısmi, {len(kabul)} tanesi kabul edilmiş "
             f"boşluk, {len(engelli)} tanesi GERÇEKTEN ENGELLİ")
    if engelli:
        adlar = ", ".join(str(r.get("entity_id")) for r in engelli[:4])
        metin += f" ({adlar})"
    metin += (". Kısmi kaynak çalışıyor ama eksik veri verir; engelli kaynak "
              "hiç veri vermez ve panelde eski rakam taze görünür.")
    return metin


def _say_sikayet_kok_neden(rows: dict[str, list]) -> str:
    v = rows.get("customer_voice", []) or []
    c = rows.get("crm_unanswered", []) or []
    if not v:
        return f"Müşteri sesi kaydı yok; {len(c)} cevapsız mesaj var."
    kova: dict[str, int] = {}
    for r in v:
        k = str(r.get("konu") or r.get("kategori") or "?")
        kova[k] = kova.get(k, 0) + 1
    ilk = sorted(kova.items(), key=lambda x: -x[1])[:3]
    return (f"{len(v)} müşteri kaydı; en çok tekrar eden konular: "
            + ", ".join(f"{k} ({n})" for k, n in ilk)
            + f". {len(c)} mesaj hâlâ cevapsız.")


def _say_tekrar_satin_alma(rows: dict[str, list]) -> str:
    m = rows.get("crm_customers", []) or []
    s = rows.get("sales_orders", []) or []
    if not m:
        return "Müşteri kaydı okunamadı."
    tekrar = [r for r in m if (_num(r, "siparis_sayisi") or 0) > 1]
    oran = (len(tekrar) / len(m) * 100) if m else 0
    return (f"{len(m)} müşteriden {len(tekrar)} tanesi birden fazla sipariş "
            f"vermiş (%{oran:.0f}). {len(s)} sipariş kaydı var. "
            "Tekrar satın alma oranı düşükse büyüme her ay sıfırdan başlar.")


# --- SEO konusmacilari (22.09.2026) ---------------------------------------
def _say_seo_icerik(rows: dict[str, list]) -> str:
    s = rows.get("urun_seo", []) or []
    if not s:
        return "SEO kaydı okunamadı; arama görünürlüğü ölçülemez."
    baslikli = [r for r in s if r.get("baslik_var")]
    aciklamali = [r for r in s if r.get("aciklama_var")]
    uzun = [r for r in s if (_num(r, "baslik_uzunluk") or 0) > 60]
    kisa_acik = [r for r in s if 0 < (_num(r, "aciklama_uzunluk") or 0) < 70]
    metin = (f"{len(s)} üründen {len(baslikli)} tanesinde SEO başlığı, "
             f"{len(aciklamali)} tanesinde açıklama tanımlı.")
    if uzun:
        metin += f" {len(uzun)} başlık 60 karakteri aşıyor (arama sonucunda kesilir)."
    if kisa_acik:
        metin += f" {len(kisa_acik)} açıklama 70 karakterin altında."
    metin += (" Tanımlı olmak işe yaradığı anlamına gelmez: sıralama verisi "
              "elimizde YOK, bu yüzden etkisi ölçülemiyor.")
    return metin


def _say_seo_anahtar(rows: dict[str, list]) -> str:
    s = rows.get("urun_seo", []) or []
    if not s:
        return "SEO kaydı okunamadı."
    anahtarli = [r for r in s if r.get("anahtar_var")]
    anasiz = [r for r in s if not str(r.get("ana_anahtar") or "").strip()]
    kova: dict[str, int] = {}
    for r in s:
        a = str(r.get("ana_anahtar") or "").strip().casefold()
        if a:
            kova[a] = kova.get(a, 0) + 1
    cakisan = {a: n for a, n in kova.items() if n > 1}
    metin = (f"{len(s)} üründen {len(anahtarli)} tanesinde anahtar kelime "
             f"tanımlı, {len(anasiz)} tanesinde ana anahtar yok.")
    if cakisan:
        ornek = ", ".join(list(cakisan)[:3])
        metin += (f" 🔴 {len(cakisan)} anahtar kelime birden fazla ürüne "
                  f"atanmış ({ornek}) — aynı kelimede kendi ürünlerimiz "
                  "birbiriyle yarışır.")
    else:
        metin += " Ana anahtar kelimeler ürünler arasında çakışmıyor."
    return metin


def _say_seo_teknik(rows: dict[str, list]) -> str:
    s = rows.get("urun_seo", []) or []
    a = rows.get("urun_alan_karsilastirma", []) or []
    if not s:
        return "SEO kaydı okunamadı."
    slugsuz = [r for r in s if not str(r.get("slug") or "").strip()]
    yayinda = [r for r in s if r.get("yayinda")]
    ad_farki = [r for r in a
                if str(r.get("alan")) == "Ürün adı"
                and str(r.get("durum")) == "FARKLI"]
    metin = (f"{len(s)} üründen {len(yayinda)} tanesi yayında; "
             f"{len(slugsuz)} tanesinde adres (slug) boş.")
    if ad_farki:
        metin += (f" {len(ad_farki)} üründe ürün adı iki platformda FARKLI — "
                  "aynı ürün iki ayrı adla indekslenir, arama gücü bölünür.")
    return metin


# --- WEB konusmacilari (22.09.2026) ---------------------------------------
def _say_web_gelistirici(rows: dict[str, list]) -> str:
    k = rows.get("urun_karti", []) or []
    o = rows.get("sayfa_olcum", []) or []
    if not k:
        return "Ürün kartı okunamadı; sayfa kapsaması çıkarılamaz."
    yayinda = [r for r in k if r.get("wix_yayinda")]
    if not o:
        return (f"{len(yayinda)} ürün yayında. Sayfaların kendisi henüz "
                "ölçülmedi, bu yüzden hangi sayfanın ne taşıdığı "
                "söylenemez.")
    urun_s = [r for r in o if r.get("tur") == "urun"]
    elde = [r for r in o if r.get("tur") == "sabit"]
    # 🔴 "ince" ile "bos" AYRI. Burada olculen sey, JS calistirmayan bir
    # istemcinin gordugudur. Sayfa kullaniciya dolu gorunuyor olabilir.
    ince_elde = [r for r in elde if r.get("jssiz_bakana_ince")]
    ince_urun = [r for r in urun_s if r.get("jssiz_bakana_ince")]
    h1siz = [r for r in elde if r.get("h1_yok")]
    ort = (sum(int(r.get("kelime_sayisi") or 0) for r in urun_s)
           // max(len(urun_s), 1))
    metin = (f"{len(yayinda)} ürün yayında. Wix'in kendi ürün sayfaları "
             f"({len(urun_s)} adet) sunucudan ortalama {ort} kelimeyle "
             f"geliyor ve {len(ince_urun)} tanesi ince.")
    if elde:
        metin += (f" Elde yapılmış {len(elde)} sayfanın {len(ince_elde)} "
                  f"tanesi JS çalıştırmayan bir bota neredeyse boş görünüyor, "
                  f"{len(h1siz)} tanesinde başlık etiketi (H1) yok.")
        metin += (" Bu sayfaların BOŞ olduğu anlamına gelmez — içerik "
                  "tarayıcıda kuruluyor; ama JS çalıştırmayan her okuyucu "
                  "için aradaki fark gerçektir.")
    return metin


def _say_sayfa_donusum(rows: dict[str, list]) -> str:
    f = rows.get("ecommerce_funnel", []) or []
    k = rows.get("urun_karti", []) or []
    if not f:
        return ("Huni verisi okunamadı; sayfaya gelenin ne kadarının satın "
                "aldığı ölçülemiyor. Dönüşüm iyileştirmesi ölçüm olmadan "
                "tahmin olur.")
    return (f"{len(f)} huni kaydı ve {len(k)} ürün okunuyor. "
            "Dönüşüm kararı sayfa değişikliğinden ÖNCE ve SONRA ölçülmeli; "
            "tek ölçümle 'iyileşti' denemez.")


def _say_site_izleme(rows: dict[str, list]) -> str:
    sis = rows.get("system", []) or []
    pr = rows.get("provenance", []) or []
    engelli = [r for r in pr
               if str(r.get("current_connection", "")).upper()
               in ("SOURCE_NOT_CONNECTED", "BLOCKED_BY_EXTERNAL_CREDENTIAL")]
    metin = f"{len(sis)} sistem kaydı, {len(pr)} kaynak izleniyor"
    if engelli:
        metin += f"; {len(engelli)} kaynak engelli"
    return (metin + ". 7/24 izleme için sayfa yanıt süresi ve hata oranı "
            "henüz toplanmıyor — bugün izlenen şey site değil, veri "
            "kaynaklarının durumu.")


def _ig_paket_eki(rol: str, rows: dict[str, list]) -> str:
    """Gunluk Instagram paketinin bu role dusen kismi (30.10.2026)."""
    paket = rows.get("ig_gunluk_paket") or []
    if not paket:
        return ""
    son = max(str(r.get("gun")) for r in paket)
    bugun = [r for r in paket if str(r.get("gun")) == son]
    urun = bugun[0].get("urun_slug")
    if rol == "video":
        cekim = [r for r in bugun if r.get("bicim") in ("REELS", "STORY")]
        onayli = sum(r.get("durum") == "ONAYLANDI" for r in cekim)
        return (f" Günlük paket {son} ({urun}): {len(cekim)} reels/story çekim "
                f"föyü hazır, {onayli} tanesi onaylı ve çekime açık.")
    if rol == "bicim":
        sayim = {}
        for r in bugun:
            sayim[r.get("bicim")] = sayim.get(r.get("bicim"), 0) + 1
        dagilim = ", ".join(f"{v} {k.lower()}" for k, v in sorted(sayim.items()))
        return f" Günlük paket {son} ({urun}) biçimleri: {dagilim}."
    if rol == "ritim":
        gun = len({str(r.get("gun")) for r in paket})
        yayin = sum(r.get("durum") == "YAYINLANDI" for r in paket)
        bekleyen = sum(r.get("durum") == "ONERI" for r in paket)
        return (f" Günlük hat 7 günde {gun} paket / {len(paket)} içerik üretti; "
                f"{yayin} yayında, {bekleyen} karar bekliyor.")
    onay = sum(r.get("durum") in ("ONAYLANDI", "YAYINLANDI") for r in paket)
    return (f" Organik: günlük paketlerden {onay}/{len(paket)} içerik onaylı "
            f"(son paket {son}, {urun}).")


def _ig_ekli(konusmaci, rol: str):
    def konus(rows: dict[str, list]) -> str:
        return konusmaci(rows) + _ig_paket_eki(rol, rows)
    konus.__name__ = getattr(konusmaci, "__name__", "konus")
    return konus


SPEAKERS: dict[str, Callable[[dict[str, list]], str]] = {
    "web_gelistirici": _say_web_gelistirici,
    "sayfa_donusum": _say_sayfa_donusum,
    "site_izleme": _say_site_izleme,
    "seo_icerik": _say_seo_icerik,
    "seo_anahtar": _say_seo_anahtar,
    "seo_teknik": _say_seo_teknik,
    "arac_envanteri_uzmani": _say_arac_envanteri,
    "arac_arastirmacisi": _say_arac_arastirmacisi,
    "surum_takipcisi": _say_surum_takipcisi,
    "erisim_denetcisi": _say_erisim_denetcisi,
    "baglanti_denetcisi": _say_baglanti_denetcisi,
    "sikayet_kok_neden": _say_sikayet_kok_neden,
    "tekrar_satin_alma": _say_tekrar_satin_alma,
    "karar_denetcisi": _say_karar_denetcisi,
    "veri_guven_denetcisi": _say_veri_guven_denetcisi,
    "oneri_denetcisi": _say_oneri_denetcisi,
    "model_denetcisi": _say_model_denetcisi,
    "alan_tutarlilik": _say_alan_tutarlilik,
    "iddia_envanteri": _say_iddia_envanteri,
    "yetki_denetcisi": _say_yetki_denetcisi,
    "kanal_kapsama": _say_kanal_kapsama,
    "firsat_takibi": _say_firsat_takibi,
    "pazaryeri_uzmani": _say_pazaryeri_uzmani,
    "marka_mimarisi": _say_marka_mimarisi,
    "marka_sagligi": _say_marka_sagligi,
    "halkla_iliskiler_muduru": _say_halkla_iliskiler_v2,
    "basin_iliskileri": _say_basin_iliskileri_v2,
    "kriz_iletisimi": _say_kriz_iletisimi,
    "itibar_izleme": _say_itibar_izleme_v2,
    "isbirligi_sorumlusu": _say_isbirligi_sorumlusu,
    "yayin_hukuk": _say_yayin_hukuk,
    "kaynakca_sorumlusu": _say_kaynakca_sorumlusu,
    "is_planlama": _say_is_planlama,
    "dizgi_baski": _say_dizgi_baski,
    "dizgi_uzmani": _say_dizgi_uzmani,
    "kesim_uzmani": _say_kesim_uzmani,
    "marka_muhafizi": _say_marka_muhafizi,
    "tasarim_metin_yazari": _say_tasarim_metin_yazari,
    "katalog_editoru": _say_katalog_editoru,
    "kitap_editoru": _say_kitap_editoru,
    "kurumsal_editor": _say_kurumsal_editor,
    "marka_kimlik": _say_marka_kimlik,
    "marka_deneyimi": _say_marka_deneyimi,
    # tasarim / Canva ekibi (22.09.2026)
    "sablon_sorumlusu": _say_sablon_sorumlusu,
    "tasarim_direktoru": _say_tasarim_direktoru,
    "produksiyon_muduru": _say_kreatif_produksiyon,
    "grafik_tasarimci": _say_grafik_tasarimci,
    "varlik_sorumlusu": _say_gorsel_varlik,
    "tasarim_mevzuat": _say_tasarim_mevzuat,
    "meta_kreatif": _say_meta_reklam_kreatifci,
    "tasarim_performans": _say_kreatif_performans_analisti,
    "video_editoru": _ig_ekli(_say_video_editoru, "video"),
    "sosyal_editor": _ig_ekli(_say_sosyal_medya_editoru, "bicim"),
    "baski_uzmani": _say_baski_katalog,
    "finance": _say_finance,
    "accounting_control": _say_accounting,
    # kreatif + marka (20.09.2026)
    "creative_decision": _say_creative_decision,
    "creative_hypothesis": _say_creative_hypothesis,
    "creative_copy": _say_creative_copy,
    "creative_fatigue": _say_creative_fatigue,
    "brand_voice": _say_brand_voice,
    "brand_positioning": _say_brand_positioning,
    "market_findings": _say_market_findings,
    "price_position": _say_price_position,
    # organik icerik (20.09.2026)
    "creative_coverage": _say_creative_coverage,
    "brand_strategy": _say_brand_strategy,
    "bizdev": _say_bizdev,
    "content_cadence": _ig_ekli(_say_content_cadence, "ritim"),
    "social_engagement": _say_social_engagement,
    "art_format": _say_art_format,
    "ecommerce_sales": _say_sales,
    "field_b2b_sales": _say_b2b,
    "meta_performance": _say_ads,
    "creative_intelligence": _say_creative,
    "social_media": _ig_ekli(_say_social, "sosyal"),
    "data_measurement": _say_measurement,
    "crm_customer": _say_crm,
    "product_portfolio": _say_products,
    "operations": _say_operations,
    "regulatory_quality": _say_decisions,
    "growth": _say_decisions,
    "ai_prompt_engineering": _say_capability,
    **department_activation.SPEAKERS,
}


def opinions(memory: Any, only: tuple[str, ...] = (), *, activity: dict | None = None,
             on_member_start: Callable[[Member], None] | None = None,
             on_member_done: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Her ekip üyesinin bu veriye bakınca söylediği. Sıfır model çağrısı.

    Veri okunamazsa uye "VERI YOK" der ve hangi sorgunun okunamadigini
    soyler. Dis arastirma gerektirenler ve sentez rolleri kendi durumlarini
    bildirir; onlara sahte bir cumle yazdirmak paneli dolu gostermek icin
    yalan olurdu.
    """
    cache: dict[str, list] = {}
    source_refs: dict[str, str] = {}
    out: list[dict[str, Any]] = []

    for member in ROSTER:
        if only and member.key not in only:
            continue
        if on_member_start:
            on_member_start(member)
        kayit: dict[str, Any] = {
            "key": member.key, "name": member.name, "job": member.job,
            "kind": member.kind, "reads": list(member.reads),
            "model_calls": 0,
        }
        recorded = (activity or {}).get(member.key, {})
        if member.mode in ("research", "synthesis") and recorded.get("status") == "PRODUCED" and recorded.get("evidence_refs") and recorded.get("statement"):
            kayit.update(status=SPEAKS, statement=recorded["statement"],
                         evidence_refs=recorded["evidence_refs"],
                         produced_items=recorded.get("items", 0),
                         activity_status="PRODUCED")
            out.append(kayit)
            if on_member_done:
                on_member_done(kayit)
            continue
        if member.mode == "research":
            kayit.update(status=NEEDS_RESEARCH,
                         statement="Şirket verisinden konuşamam; dış kaynak "
                                   "araştırması gerekir.")
            out.append(kayit)
            if on_member_done:
                on_member_done(kayit)
            continue
        if member.mode == "synthesis":
            kayit.update(status=NEEDS_INPUT,
                         statement="Kendi verim yok; diğerlerinin bulgusunu "
                                   "girdi alırım.")
            out.append(kayit)
            if on_member_done:
                on_member_done(kayit)
            continue

        rows: dict[str, list] = {}
        eksik: list[str] = []
        for query in member.reads:
            if query in cache:
                rows[query] = cache[query]
                continue
            try:
                evidence = memory._fetch(query)
                kayitlar = list(evidence.records)
            except Exception:  # noqa: BLE001 - okunamayan sorgu bir durumdur
                eksik.append(query)
                continue
            cache[query] = kayitlar
            source = str(getattr(evidence, "source", ""))
            source_refs[query] = (source if source.startswith("postgres:") and
                                  getattr(evidence, "authority", "") == "CANONICAL_COMPANY_MEMORY" else "")
            rows[query] = kayitlar

        kayit["evidence_refs"] = list(dict.fromkeys(
            source_refs.get(query, "") for query in rows
            if rows[query] and source_refs.get(query)))
        konusmaci = SPEAKERS.get(member.key)
        if eksik and not rows:
            kayit.update(status=NO_DATA, missing=eksik,
                         statement="Okuması gereken veri açık değil: "
                                   + ", ".join(eksik))
        elif member.key in department_activation.SPEAKERS and not any(rows.values()):
            kayit.update(status=NO_DATA, missing=list(member.reads),
                         statement="Okunabilen kaynaklarda ilgili kayıt yok; iş bekliyor.")
        elif konusmaci is None:
            okunan = sum(len(r) for r in rows.values())
            kayit.update(
                status=ISLEV_YOK,
                rows={q: len(r) for q, r in rows.items()},
                statement=(
                    f"Okuduğu kaynaklarda {okunan} satır var ve erişilebiliyor; "
                    "eksik olan veri değil, bu üyenin o satırlara bakınca ne "
                    "söyleyeceğini tanımlayan işlev. Yazılana kadar susuyor."))
        else:
            try:
                kayit.update(status=SPEAKS, statement=konusmaci(rows),
                             rows={q: len(r) for q, r in rows.items()})
                if eksik:
                    kayit["missing"] = eksik
            except Exception as exc:  # noqa: BLE001
                kayit.update(status=ISLEM_HATASI, statement=type(exc).__name__)
        out.append(kayit)
        if on_member_done:
            on_member_done(kayit)
    return out
