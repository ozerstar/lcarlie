#!/usr/bin/env python3
"""Bounded inbound Meta conversation sync using existing Page token. No sends."""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jarvis.data_completion import conversation_sql, quote
import subprocess


def settings():
    result={}
    for line in Path('/opt/lcarlie/n8n/.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key,value=line.split('=',1)
            result[key]=value.strip().strip('"').strip("'")
    return result


def sql(statement):
    r=subprocess.run(['docker','exec','-i','lcarlie-postgres','psql','-X','-q','-v','ON_ERROR_STOP=1','-U','n8n','-d','n8n','-f','-'],input=statement,capture_output=True,text=True)
    if r.returncode:
        raise RuntimeError('Database sync failed')


def get(url, token):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='graph.facebook.com':
        raise ValueError('Unexpected pagination destination')
    params=urllib.parse.parse_qsl(parsed.query,keep_blank_values=True)
    # Tokens are sent only in headers; never written to diagnostics.
    url=urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode([(k,v) for k,v in params if k!='access_token'])))
    request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=30) as response:
        return json.load(response)


def pages(url,token,limit):
    rows=[]
    for _ in range(limit):
        j=get(url,token)
        rows.extend(j.get('data',[]))
        url=(j.get('paging') or {}).get('next')
        if not url:
            return rows,True,None
    parsed=urllib.parse.urlparse(url)
    safe=urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(parsed.query) if k!='access_token'])))
    return rows,False,safe


def main():
    env=settings()
    page=env.get('FB_PAGE_ID','');token=env.get('FB_PAGE_TOKEN','')
    if not page or not token:
        raise ValueError('Existing Page credentials missing')
    own={page,env.get('IG_USER_ID','')}-{''}
    summaries=[]
    checkpoint_path=Path(os.environ.get('JARVIS_STATE_DIR','/opt/lcarlie/jarvis-phase2/state'))/'data-sync'/'meta-checkpoint.json'
    checkpoint_path.parent.mkdir(parents=True,exist_ok=True)
    try:checkpoints=json.loads(checkpoint_path.read_text())
    except (OSError,ValueError):checkpoints={}
    for channel in ('instagram','messenger'):
        result={'channel':channel,'conversations':0,'messages':0,'errors':0,'history_complete':True}
        try:
            params={'fields':'id,participants,messages.limit(20){id,created_time,from,message}','limit':50}
            if channel=='instagram':
                params['platform']='instagram'
                params['fields']='id,participants'
            root_url='https://graph.facebook.com/v21.0/'+page+'/conversations?'+urllib.parse.urlencode(params)
            records,complete,next_url=pages(root_url,token,1 if channel=='instagram' else 10)
            if channel=='instagram':
                if checkpoints.get(channel):
                    older,complete,next_url=pages(checkpoints[channel],token,1)
                    records=list({r['id']:r for r in records+older}.values())
                checkpoints[channel]=next_url

            result['history_complete']=complete
            for record in records:
                try:
                    if channel=='instagram':
                        message_url='https://graph.facebook.com/v21.0/'+record['id']+'/messages?'+urllib.parse.urlencode({'fields':'id,created_time,from,message','limit':20})
                        batch=get(message_url,token)
                        record['messages']=batch
                    else:
                        batch=record.get('messages',{})
                    messages=list(batch.get('data',[]))
                    more=(batch.get('paging') or {}).get('next')
                    message_complete=True
                    if more:
                        older,message_complete,_=pages(more,token,1 if channel=='instagram' else 4)
                        messages+=older
                    if not messages:
                        continue
                    sql(conversation_sql(channel,record,messages,own,message_complete))
                    result['conversations']+=1;result['messages']+=len(messages)
                    result['history_complete'] &= message_complete
                except Exception as exc:  # noqa: BLE001 - isolated failures expose only types/counts
                    result['errors']+=1;result['error_type']=type(exc).__name__
            result['status']='SUCCESS' if not result['errors'] and result['history_complete'] else 'PARTIAL'
            if result['conversations']:
                gap='Read-only Page API works; bounded historical message sync. Attribution identity remains unverified.'
                sql("UPDATE core.source_authority SET current_connection='PARTIAL',gap="+quote(gap)+",dogrulama_zamani=now(),dogrulama_yontemi='Live Graph read + idempotent message ingestion' WHERE alan="+quote('conversation_'+channel)+';')
        except urllib.error.HTTPError as exc:
            result.update(status='FAILED',http_status=exc.code)
        except Exception as exc:  # noqa: BLE001
            result.update(status='FAILED',error_type=type(exc).__name__)
        sql("INSERT INTO raw.yukleme_log(kaynak,durum,okunan,yazilan,guncellenen,mesaj,baslangic,bitis) VALUES ("+quote('meta_messages_'+channel)+','+quote(result['status'])+','+str(result['messages'])+','+str(result['messages'])+",0,"+quote(json.dumps(result))+',now(),now());')
        summaries.append(result)
    temporary=checkpoint_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(checkpoints))
    os.chmod(temporary,0o600)
    temporary.replace(checkpoint_path)
    print(json.dumps(summaries))
    return 1 if any(r['status']=='FAILED' for r in summaries) else 0


if __name__=='__main__':sys.exit(main())
