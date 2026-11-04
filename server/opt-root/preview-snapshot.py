import json,sys
from pathlib import Path
sys.path.insert(0,'/opt/lcarlie/jarvis-phase2')
from webconsole import app
p=app._panel_ekip()
# Limit to roster fields needed by the visual preview; no observations or personal data.
for d in p['departmanlar']:
 for m in d.get('uyeler',[]):
  for k in list(m):
   if k not in ('key','ad','gorev','durum','sorumlu_mu','okur'):del m[k]
Path('/opt/lcarlie/office-preview-data.json').write_text(json.dumps(p,ensure_ascii=False,default=str))
print('Preview snapshot saved')
