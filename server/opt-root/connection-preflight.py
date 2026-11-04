import json,sys
sys.path.insert(0,'/opt/lcarlie/jarvis-phase2')
from webconsole import app
result={}
for q in ['ecommerce_funnel','urun_karti','provenance','crm_customers','sales_orders','customer_voice','crm_unanswered','market_research','content_performance']:
 try:
  e=app._memory._fetch(q);result[q]={'count':len(e.records),'source':e.source}
 except Exception as e:result[q]={'error':type(e).__name__}
print(json.dumps(result,ensure_ascii=False))
