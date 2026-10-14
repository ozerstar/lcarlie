"""Validated, transactional inbound data refresh. No outbound messaging."""
from __future__ import annotations
import json
from datetime import date, datetime
from decimal import Decimal


def quote(value):
    return "'"+str(value).replace("'", "''")+"'"


def day(value):
    return datetime.strptime(str(value), '%Y%m%d').date().isoformat()


def ga4_replace_sql(funnel, purchases, start, end):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if start > end or not funnel:
        raise ValueError('A valid nonempty funnel snapshot is required')
    values = []
    for row in funnel:
        observed = day(row['date'])
        if not start <= date.fromisoformat(observed) <= end:
            raise ValueError('Event outside requested interval')
        event = str(row['eventName'])
        if not event or len(event)>128 or int(row['eventCount'])<0:
            raise ValueError('Invalid aggregate event')
        values.append('('+','.join([quote(event),quote(observed),'NULL','NULL','NULL','NULL',"'OBSERVED'","'GUNLUK_TOPLAM'",quote(json.dumps(row,ensure_ascii=False))+'::jsonb'])+')')
    for row in purchases:
        observed = day(row['date'])
        if not start <= date.fromisoformat(observed) <= end:
            raise ValueError('Purchase outside requested interval')
        revenue = Decimal(str(row.get('purchaseRevenue') or '0'))
        if not revenue.is_finite():
            raise ValueError('Nonfinite revenue')
        transaction = str(row.get('transactionId') or '')
        if not transaction or transaction=='(not set)':
            continue  # daily purchase count is already represented by the funnel snapshot
        values.append('('+','.join(["'purchase'",quote(observed),quote(transaction),quote(row.get('sessionSource') or ''),quote(row.get('sessionMedium') or ''),str(revenue),"'OBSERVED'","'GUNLUK_TOPLAM'",quote(json.dumps(row,ensure_ascii=False))+'::jsonb'])+')')
    sql = 'BEGIN; SELECT pg_advisory_xact_lock(41020261014);\n'
    # Replace only this loader's daily aggregates, never raw individual events.
    sql += "DELETE FROM raw.ga4_event WHERE granulerlik='GUNLUK_TOPLAM' AND kanit_durumu='OBSERVED' AND event_date BETWEEN "+quote(start)+'::date AND '+quote(end)+'::date;\n'
    for i in range(0,len(values),500):
        sql += 'INSERT INTO raw.ga4_event(event_name,event_date,transaction_id,source,medium,value,kanit_durumu,granulerlik,ham) VALUES '+','.join(values[i:i+500])+' ON CONFLICT DO NOTHING;\n'
    sql += "UPDATE core.source_authority SET current_connection='CONNECTED',dogrulama_zamani=now(),dogrulama_yontemi='Live GA4 Data API + atomic aggregate refresh',gap='Daily aggregate data is connected; GA4 is not commercial revenue authority. Cart instrumentation requires separate verification.' WHERE alan='behavior';\n"
    sql += "UPDATE core.funnel_adim SET enstrumantasyon='PARTIAL',olcum_zamani=now(),olcum_yontemi='GA4 Data API daily aggregate',olcum_kaniti='view_cart aggregate observed; consent-limited cart views, not unique-person conversion' WHERE adim_kod='VIEW_CART' AND EXISTS (SELECT 1 FROM raw.ga4_event WHERE event_name='view_cart' AND event_date>=DATE '2026-10-14' AND (ham->>'eventCount')::numeric>0);\n"
    sql += "INSERT INTO raw.yukleme_log(kaynak,durum,okunan,yazilan,guncellenen,mesaj,baslangic,bitis) VALUES ('ga4','SUCCESS',"+str(len(funnel)+len(purchases))+','+str(len(values))+",0,'Atomic GA4 daily aggregate refresh',now(),now()); COMMIT;"
    return sql, len(values)


def conversation_sql(channel, record, messages, own_ids, complete):
    if channel not in ('instagram','messenger') or not record.get('id'):
        raise ValueError('Invalid conversation')
    participants = record.get('participants',{}).get('data',[])
    customer_ids = {str(r['id']) for r in participants if r.get('id') and str(r['id']) not in own_ids}
    if len(customer_ids)!=1:
        raise ValueError('Ambiguous customer identity')
    customer = next(iter(customer_ids))
    normalized = []
    for row in messages:
        sender = str((row.get('from') or {}).get('id') or '')
        if not row.get('id') or not sender or sender not in own_ids|customer_ids:
            raise ValueError('Message sender or ID is missing/ambiguous')
        ts = datetime.fromisoformat(str(row['created_time']).replace('Z','+00:00'))
        if ts.tzinfo is None:
            raise ValueError('Message timezone missing')
        normalized.append((str(row['id']),ts.isoformat(),'giden' if sender in own_ids else 'gelen',sender,str(row.get('message') or '')))
    if not normalized:
        raise ValueError('No readable messages')
    first = min(r[1] for r in normalized)
    last = max(r[1] for r in normalized)
    notes = json.dumps({'meta_sync':{'history_complete':complete,'source':'Graph read-only'}},ensure_ascii=False)
    sql = 'BEGIN; SELECT pg_advisory_xact_lock(41020261015);\n'
    sql += "INSERT INTO lcarlie.konusma(kanal,harici_id,musteri_ref,ilk_mesaj,son_mesaj,notlar) VALUES ("+','.join(map(quote,[channel,record['id'],customer,first,last,notes]))+"::jsonb) ON CONFLICT(kanal,harici_id) DO UPDATE SET guncelleme=now(),notlar=lcarlie.konusma.notlar||excluded.notlar;\n"
    where = 'kanal='+quote(channel)+' AND harici_id='+quote(record['id'])
    for external,ts,direction,sender,body in normalized:
        sql += 'INSERT INTO lcarlie.mesaj(konusma_id,harici_id,zaman,yon,gonderen,metin) SELECT id,'+','.join(map(quote,[external,ts,direction,sender,body]))+' FROM lcarlie.konusma WHERE '+where+' ON CONFLICT(konusma_id,harici_id) DO UPDATE SET zaman=excluded.zaman,yon=excluded.yon,gonderen=excluded.gonderen,metin=excluded.metin;\n'
    sql += 'UPDATE lcarlie.konusma k SET ilk_mesaj=(SELECT min(zaman) FROM lcarlie.mesaj WHERE konusma_id=k.id),son_mesaj=(SELECT max(zaman) FROM lcarlie.mesaj WHERE konusma_id=k.id),mesaj_sayisi=(SELECT count(*) FROM lcarlie.mesaj WHERE konusma_id=k.id),guncelleme=now() WHERE '+where+'; COMMIT;'
    return sql
