"""What an invoice line is about, and which of the two businesses it belongs to.

Owner, 02.11.2026: "Lemos ve L'CARLIÉ aynı şirket ama 2 farklı iş gibi çalışıyor. Muayenehanede
yapılan satış, etkinlikler buraya geliyor; L'CARLIÉ'nin satılan ürünleri de giriyor. Faturaya göre
bunları analiz edip ayıklamak gerekiyor, içeriklerine göre." Deterministic rules on the line text
(and the supplier when the lines could not be read); shared costs are split later by sales share.
"""
import re

from money_ledger import plain

LCARLIE_PRODUCTS = {  # name in the line → product (barcodes 8684869609… are L'CARLIÉ's)
    "vireon": "Vireon", "virean": "Vireon", "femisia": "Femisia", "hydravie": "Hydravie", "luciderm": "Luciderm",
    "lipvora": "Lipvora", "liftelle": "Liftelle", "dermaguard": "Dermaguard", "dermanova": "Dermanova",
    "cal jaw": "Cal Jaw", "caljaw": "Cal Jaw", "intimblanc": "Intimblanc", "optywave": "Optywave", "sunacnea": "Sunacnea",
    "babyrescue": "Babyrescue", "calmaros": "Calmaros", "minisooth": "Minisooth", "oragarde": "Oragarde",
    "seralimbo": "Seralimbo", "buguard": "Buguard", "dorsivia": "Dorsivia", "kinesis": "Kinesis+",
}
_BRAND = re.compile(r"l\s*'?\s*carli|lcarlia|lcarlie|8684869609\d{3}")

THEMES = {
    "lcarlie_urun": "L'CARLIÉ ürünü", "takviye_ilac": "Takviye / ilaç", "promosyon_matbaa": "Promosyon / matbaa / baskı",
    "ambalaj": "Ambalaj / kutu", "pazaryeri": "Pazaryeri (Trendyol vb.)", "kargo": "Kargo / kurye",
    "reklam": "Reklam", "etkinlik_ikram": "Etkinlik / organizasyon / ikram", "saglik_hizmeti": "Sağlık / muayene hizmeti",
    "grup_ici": "Grup içi (MOY ↔ Lemos)", "iletisim": "Telefon / internet", "arac": "Araç / bakım", "ofis_demirbas": "Ofis / demirbaş / kırtasiye",
    "yazilim": "Yazılım / barkod / sistem", "danismanlik": "Danışmanlık / hizmet", "giyim": "Giyim",
    "numune_tester": "Tester / numune (ücretsiz dağıtım)",
    "diger": "Diğer",
}
_RULES = (  # order matters: the first match wins
    ("grup_ici", r"moy dan|moy danisman"),
    ("pazaryeri", r"platform hizmet|komisyon|termin gecikme|tazmin|trendyol|hepsiburada|dsm grup"),
    ("kargo", r"kargo|desi|kurye|nakliye|gonderi"),
    ("reklam", r"reklam bedeli|reklam hizmet|meta|google ads"),
    ("arac", r"otomobil|arac muayene|muayene istasyon|balata|egzoz|lastik|rot balans|motorlu arac|yag degisim|falken|michelin|\d{3}/\d{2}r\d{2}|kare yama"),
    ("takviye_ilac", r"gida takviye|takviye|ilac|eczane|schussler|zerre|nattopro|diamix|vitamin|kapsul|tablet|sase|surup|hidrosol|bioremedy|pharma|altin-|gumus|kolloid"),
    ("promosyon_matbaa", r"baski|matbaa|promosyon|dtf|brosur|katalog|kartvizit|afis|etiket|kutu harf|isikli|canta|kalem|ajans|tabela|roll ?up|banner|kitap|bayrak"),
    ("ambalaj", r"ambalaj|koli|mukavva|sunger|kagitcilik|poset|kutu|sise|kavanoz|plastik"),
    ("etkinlik_ikram", r"organizasyon|kongre|dernegi|arastirma|stand|otel|konaklama|turizm|baklava|cikolata|pasta|ikram|yemek|catering|icecek|festa|liva"),
    ("iletisim", r"tt mobil|mobil hat|telefon|internet|turkcell|vodafone"),
    ("yazilim", r"yazilim|lisans|gs1|barkod|e-fatura|bilisim|teknoloji|idata|zirve"),
    ("ofis_demirbas", r"mobilya|kirtasiye|bilgisayar|ofis|koltuk|masa|baglanti|bauhaus|insaat malz|ev gerec|nalbur"),
    ("giyim", r"giyim|kigili|tekstil|elbise"),
    ("saglik_hizmeti", r"muayene|seans|tedavi|uygulama|kontrol|enjeksiyon|terapi|serum"),
    ("danismanlik", r"danismanlik|hizmet bedeli|muhasebe|musavir"),
)
BUSINESSES = {"lcarlie": "L'CARLIÉ", "lemos": "Lemos (muayenehane)", "ortak": "Ortak / bölüştürülen",
              "belirsiz": "Belirsiz (sahibe sorulacak)", "grup": "Grup içi (MOY)"}
# whose cost/sale is it; "ortak" is split by the period's sales share
_OUT_BUSINESS = {"lcarlie_urun": "lcarlie"}  # every other sale is the clinic's
_IN_BUSINESS = {"lcarlie_urun": "lcarlie", "ambalaj": "lcarlie", "pazaryeri": "lcarlie", "kargo": "lcarlie",
                "takviye_ilac": "lemos", "saglik_hizmeti": "lemos"}


def product_of(name):
    """A L'CARLIÉ product only when the line starts with the brand or its barcode: "DTF BASKI
    DTF L CARLIE" is printing done for L'CARLIÉ, not a product."""
    text = plain(name).replace("é", "e")
    for key, product in LCARLIE_PRODUCTS.items():  # these names are L'CARLIÉ's alone: "VİREAN", "optywave"
        if re.search(rf"(^|[^a-z]){key}([^a-z]|$)", text) or text.startswith(("lcarlie" + key, "l'carlie" + key)):
            return product
    starts =re.match(r"^\W*(?:\d{6,}\s+)?(?:l\s*'?\s*carli[ea]|lcarlia|lcarlie)\b\W*([a-z][a-z+]*)?", text)
    coded = re.match(r"^\W*8684869609\d{3}\W+([a-z][a-z+]*)", text)
    if not starts and not coded and not re.search(r"8684869609\d{3}", text):
        return ""
    for key, product in LCARLIE_PRODUCTS.items():
        if key in text:
            return product
    word = (starts and starts.group(1)) or (coded and coded.group(1))
    return word.title() if word else "L'CARLIÉ (adı yok)"


def classify(box, name, party=""):
    """(theme, business, product) for one line; the supplier helps when the line says little."""
    product = product_of(name)
    # owner, 02.11.2026: "testerlar dağıtılıyor, onlar ürün olarak sayılmaz" — a tester of a
    # L'CARLIÉ product is the brand's give-away cost, never stock or product cost
    if product and re.search(r"(^|[^a-z])(tester|numune|deneme boy)([^a-z]|$)", plain(name)):
        return "numune_tester", "lcarlie", ""
    if product:
        return "lcarlie_urun", "lcarlie", product
    text = plain(f"{name} {party}")
    theme = next((key for key, pattern in _RULES if re.search(pattern, text)), "diger")
    if theme == "grup_ici":
        return theme, "grup", ""
    if box == "out":
        # owner, 02.11.2026: L'CARLIÉ products always appear by name on invoices; a bare
        # "gıda takviyesi" sale is another supplement the clinic sells
        return theme, _OUT_BUSINESS.get(theme, "lemos"), ""
    business = _IN_BUSINESS.get(theme, "ortak")
    if _BRAND.search(plain(name)):  # "DTF BASKI DTF L CARLIE…": printed for L'CARLIÉ
        business = "lcarlie"
    return theme, business, ""
