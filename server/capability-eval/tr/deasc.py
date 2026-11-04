import json, time
from turkish.deasciifier import Deasciifier
CASES = ["nasilsin", "iyi aksamlar", "kampanyayi kapat", "musteri sikayeti",
         "urunu siteden kaldir", "gunaydin", "tesekkurler"]
t0 = time.perf_counter()
out = {c: Deasciifier(c).convert_to_turkish() for c in CASES}
print(json.dumps({"ms_total": round((time.perf_counter()-t0)*1000, 2), "out": out},
                 ensure_ascii=False, indent=1))
