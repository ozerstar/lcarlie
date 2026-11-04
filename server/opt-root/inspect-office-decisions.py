import sys,json,os
sys.path.insert(0,'/opt/lcarlie/jarvis-phase2')
from jarvis.memory import CompanyMemory
m=CompanyMemory(host=None);e=m._fetch('decision_summary');print(json.dumps({'count':len(e.records),'rows':e.records[:2]},ensure_ascii=False))
print('web_state',os.environ.get('JARVIS_WEB_STATE_DIR'))
