import json
from pathlib import Path
d=json.loads(Path('/opt/lcarlie/jarvis-phase2/state/katalog.json').read_text())
u=d['urunler'][0]
print(list(d));print(list(u));print({k:v for k,v in u.items() if k in ('id','urun_id','slug','ad','gorsel','sku','gorseller')})
Path('/opt/lcarlie/office-catalog-fixture.json').write_text(json.dumps(d,ensure_ascii=False))
