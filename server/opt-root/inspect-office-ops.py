import sys,json
sys.path.insert(0,'/opt/lcarlie/jarvis-phase2')
from webconsole import app
from pathlib import Path
data={}
for q in ['departments','open_work','agenda','urun_karti','ecommerce_profitability','ecommerce_price','provenance']:
 try:
  e=app._memory._fetch(q); rows=list(e.records);data[q]={'source':e.source,'read_at':str(e.retrieved_at),'records':rows};print(json.dumps({'query':q,'count':len(rows),'keys':list(rows[0]) if rows else [],'sample':rows[:1] if q in ['departments','provenance'] else []},ensure_ascii=False,default=str))
 except Exception as ex:print(q,type(ex).__name__)
Path('/opt/lcarlie/office-ops-fixture.json').write_text(json.dumps(data,ensure_ascii=False,default=str))
