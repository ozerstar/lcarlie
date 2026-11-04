import json,sys,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,'/opt/lcarlie/jarvis-phase2')
from webconsole import app
p=app._panel_ekip();h=app._panel_holding();assert not h['organisation'].get('error');assert len(h['portfolio'])>0
assert all(not row['confirmed_profit'] for row in h['portfolio'])
assert p['ozet']['departman']==50
assert not any(f['kind']=='manager' for f in p['ik']['findings'])
responses={}
for path in ['/office.html','/office.js','/office.css','/api/panel/holding','/api/panel/ekip']:
 try:
  with urllib.request.urlopen('http://127.0.0.1:8091'+path) as r:responses[path]=r.status
 except urllib.error.HTTPError as e:responses[path]=e.code
assert responses['/api/panel/holding']==401
assert responses['/office.html']==200
print(json.dumps({'summary':p['ozet'],'missing':p['ik']['source_missing'],'partial':p['ik']['source_partial'],'portfolio_rows':len(h['portfolio']),'source_errors':[s for s in h['sources'] if s['status']!='read'],'http':responses,'remaining_disconnected':[d['kod'] for d in p['departmanlar'] if d['birim_durumu']=='YOK']},ensure_ascii=False,default=str))
Path('/opt/lcarlie/office-preview-data.json').write_text(json.dumps(p,ensure_ascii=False,default=str))
Path('/opt/lcarlie/office-preview-agents.json').write_text(json.dumps(app._panel_ajanlar(),ensure_ascii=False,default=str))
