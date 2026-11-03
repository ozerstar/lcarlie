"""04.11.2026: büyüme araştırmasını ekiplere okut-yorumlat; EXEC karar notu sahibe Jarvis'ten gitsin.
Kullanım (sunucu, root): /opt/lcarlie/jarvis-phase2/venv/bin/python rapor-gorev-ekle.py [--kuru]"""
import importlib.util
import json
import sys
from pathlib import Path

KOK = Path("/opt/lcarlie/jarvis-phase2")
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "scripts"))
spec = importlib.util.spec_from_file_location("iu_betik", KOK / "scripts" / "is-uretici.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from jarvis.is_uretici import IsUretici  # noqa: E402

kuru = "--kuru" in sys.argv
CIKTI = ("1) Bölümün özeti: 5 madde. 2) Bizim için anlamı: bizim verimizle (satış, reklam, ürün) "
         "karşılaştır; tutan ve tutmayan noktalar. 3) Bu hafta yapılacak 3 somut iş (sorumlu birimle). "
         "4) Katılmadığımız, eksik ya da riskli bulduğumuz noktalar.")
KABUL = "Her madde bölümdeki bir bilgiye ya da bizim verimize dayanıyor; [YARGI] olanlar ayrıca belirtilmiş"
BOLUMLER = [
    ("DATA_BI", "rapor-1-teshis", "Teşhis: neden satamıyoruz bölümünü bizim verimizle sına"),
    ("MARKETPLACE", "rapor-2-kasim-takvimi", "Kasım 2026 takvimi ve indirim hukuku bölümünü yorumla"),
    ("META_MEDIA", "rapor-3a-meta-hukuk", "Meta reklamları ve iddia hukuku bölümünü yorumla"),
    ("COPY", "rapor-3b-meta-hook", "15 hook kalıbını bizim ürünlere göre değerlendir"),
    ("UGC", "rapor-4-ugc", "UGC senaryo çerçevesi ve örnek senaryoları yorumla"),
    ("BIZDEV", "rapor-5-pazaryeri", "Pazaryeri büyümesi bölümünü yorumla"),
    ("EXPORT", "rapor-6a-ihracat-pazar", "Yurtdışı hedef pazarlar ve marj bölümünü yorumla"),
    ("EXPORT", "rapor-6c-ihracat-kanallar", "Distribütör bulma kanalları bölümünü yorumla"),
    ("FINANCE", "rapor-6b-ihracat-partner", "Ortak kazanım süreci ve ihracat fiyatı riskini yorumla"),
    ("RED_TEAM", "rapor-7-30-gun-plan", "30 günlük büyüme planını sorgula: gerçekçi mi, risk ne"),
    ("REGULATORY", "rapor-8-jarvis-egitimi", "Jarvis eğitim kurallarını mevcut metin ve işleyişimizle karşılaştır"),
]

iu = IsUretici(m._ortam(canli_arastirma=False), kuru=kuru)
kilit = None if kuru else m._kilit()  # noqa: F841
tarih = iu._gun()
agac = iu.agac_deposu.oku()
deps = {d.kod: d for d in iu.o.departmanlar()}
idler = []
for i, (kod, bilgi, baslik) in enumerate(BOLUMLER, 1):
    dep = deps.get(kod)
    if dep is None or not dep.uyeler:
        print("ATLANDI (kadro yok):", kod)
        continue
    g = {"baslik": f"Büyüme araştırması · {baslik}", "tip": "ANALIZ", "sorumlu": dep.uyeler[0].key,
         "cikti": CIKTI, "kabul_olcutu": KABUL, "sure_gun": 1, "hedef_id": "",
         "neden": "Sahip 04.11: araştırmayı ekip okusun, yorumlasın", "bilgi": [bilgi], "bilgi_sinir": 6000,
         "oncelik": "ACIL"}
    x = iu._gorev_ekle(agac, dep, g, "rapor", tarih, i, gid=f"{tarih}-{kod}-rapor{i}")
    if x:
        idler.append(x["id"])
exec_ = deps["EXEC"]
g = {"baslik": "Büyüme araştırması · ekip yorumlarından sahibe karar notu", "tip": "TASLAK",
     "sorumlu": exec_.uyeler[0].key,
     "cikti": ("Sahibe tek sayfa: 1) Araştırmanın 5 ana bulgusu. 2) Ekiplerin katıldığı ve itiraz ettiği noktalar "
               "(hangi ekip). 3) Kasım için önerilen 5 karar, her biri sahibin onayı gerekip gerekmediğiyle. "
               "4) Bu hafta ekiplerin başlayacağı işler."),
     "kabul_olcutu": "Her bulgu bir ekip teslimine ya da rapor bölümüne dayanıyor; ekip adı yazılı",
     "sure_gun": 2, "hedef_id": "", "neden": "Sahip 04.11: araştırma bana Jarvis'ten gelsin",
     "bilgi": ["rapor-7-30-gun-plan"], "bilgi_sinir": 2500, "bagimli": idler, "sahibe_gonder": True, "guclu": True,
     "oncelik": "ACIL"}
x = iu._gorev_ekle(agac, exec_, g, "rapor", tarih, 99, gid=f"{tarih}-EXEC-rapor-karar")
if not kuru:
    iu.agac_deposu.yaz(agac, iu.o.saat())
print(json.dumps({"ekip_gorevi": idler, "karar_notu": (x or {}).get("id"), "kuru": kuru, "kayit": iu.kayit},
                 ensure_ascii=False))
