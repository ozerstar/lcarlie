import sys,json
sys.path.insert(0,'/opt/lcarlie/jarvis-phase2/webconsole')
from personal_action_store import _connect
with _connect() as conn,conn.cursor() as cur:
 cur.execute("SELECT account_id,owner,name,note FROM core.jarvis_cari_account WHERE lower(name) LIKE %s OR lower(name) LIKE %s OR lower(name) LIKE %s",('%sincan%','%ülkem%','%ulkem%'))
 accounts=cur.fetchall()
 for a in accounts:
  cur.execute("SELECT entry_id,reverses,document_date,payload FROM core.jarvis_cari_entry WHERE owner=%s AND account_id=%s ORDER BY created_at DESC LIMIT 100",(a['owner'],a['account_id']))
  rows=cur.fetchall(); reversed_ids={r['reverses'] for r in rows if r['reverses']}
  a['entry_count_in_read']=len(rows)
  a['active_entries']=[{'id':r['entry_id'],'date':str(r['document_date']),'kind':r['payload'].get('kind'),'reference':r['payload'].get('reference'),'note':r['payload'].get('note'),'items':r['payload'].get('items',[])} for r in rows if not r['reverses'] and r['entry_id'] not in reversed_ids]
  cur.execute("SELECT draft_id,body FROM core.jarvis_cari_draft WHERE owner=%s AND account_id=%s AND status='draft' ORDER BY created_at DESC LIMIT 10",(a['owner'],a['account_id']))
  a['drafts']=cur.fetchall()
print(json.dumps(accounts,ensure_ascii=False,default=str))
