"""Evidence-backed organisation, portfolio and work views; no external writes."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STRUCTURE = {
    'entities': [{'id':'jarvis','name':'Jarvis','kind':'organisation','parent_id':None},
                 {'id':'lcarlie','name':"L’CARLIÉ",'kind':'brand','parent_id':'jarvis'}],
    'department_entity': {'GOOGLE_ADS':'lcarlie'},
    'note':'Yönetim görünümüdür; hukuki holding/iştirak ilişkisi iddiası değildir.'}


def structure(departments, config=None):
    if config is None:
        path=Path(os.environ.get('JARVIS_STATE_DIR','/opt/lcarlie/jarvis-phase2/state'))/'holding'/'structure.json'
        try: config=json.loads(path.read_text())
        except (OSError, ValueError): config=DEFAULT_STRUCTURE
    if not isinstance(config,dict): raise ValueError('Organizasyon bir nesne olmalı')
    entities=config.get('entities', [])
    by_id={e['id']:e for e in entities if isinstance(e,dict) and e.get('id') and e.get('name')}
    if len(by_id)!=len(entities): raise ValueError('Organizasyon kimlikleri benzersiz olmalı')
    for key in by_id:
        visited=set(); current=key
        while current is not None:
            if current in visited or current not in by_id: raise ValueError('Geçersiz üst birim ilişkisi')
            visited.add(current); current=by_id[current].get('parent_id')
    mappings=config.get('department_entity',{})
    groups={}
    for d in departments:
        entity=mappings.get(d['kod'])
        if entity not in by_id:entity=None
        family=d.get('aile') or 'Diğer'
        group=groups.setdefault((entity,family), {'entity_id':entity,'family':family,'departments':[]})
        group['departments'].append(d['kod'])
    return {'entities':list(by_id.values()),'groups':list(groups.values()),
            'unassigned':sum(len(g['departments']) for g in groups.values() if g['entity_id'] is None),
            'note':config.get('note','Organizasyon görünümü erişim yetkilerini değiştirmez.')}


def finite(value):
    if value is None or isinstance(value,bool):return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None


def portfolio(profit_rows, cards):
    by_name={}
    for row in cards:by_name.setdefault(row.get('urun_adi'),[]).append(row)
    result=[]
    for row in profit_rows:
        matches=by_name.get(row.get('urun_adi'),[])
        card=matches[0] if len(matches)==1 else {}
        source=str(card.get('maliyet_kaynagi') or '')
        # Completeness of a cost column is not evidence that its value is measured.
        estimated=any(x in source.casefold() for x in ('tahmin','varsay','estimate','default'))
        coverage=finite(row.get('kapsama_yuzde'))
        reliability='Eksik maliyet' if coverage is None or coverage<100 else 'Maliyet doğrulaması gerekli'
        if estimated:reliability='Tahmini maliyet'
        result.append({'name':row.get('urun_adi'),'revenue':finite(row.get('ciro_net')),
                       'margin_recorded':finite(row.get('brut_marj')),'coverage':coverage,
                       'cost_source':source or 'Kaynak eşleşmesi yok','reliability':reliability,
                       'source':row.get('source') or 'ecommerce_profitability',
                       'confirmed_profit':False})
    return result


def snapshot(memory):
    datasets={}; sources=[]
    for query in ('departments','ecommerce_profitability','urun_karti','agenda','open_work','provenance'):
        try:
            ev=memory._fetch(query); datasets[query]=list(ev.records)
            sources.append({'query':query,'source':ev.source,'count':len(ev.records),
                            'read_at':getattr(ev,'retrieved_at',None),'status':'read'})
        except Exception:  # noqa: BLE001
            datasets[query]=[];sources.append({'query':query,'status':'unavailable'})
    try:org=structure(datasets['departments'])
    except (ValueError,TypeError,KeyError):org={'error':'Organizasyon yapılandırması geçersiz','entities':[],'groups':[]}
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'organisation':org,
            'portfolio':portfolio(datasets['ecommerce_profitability'],datasets['urun_karti']),
            'agenda':datasets['agenda'],'open_work':datasets['open_work'],
            'record_limit':25,'sources':sources,'read_only':True,
            'google_ads_targets':{'email':'moy.ozeryildiz@gmail.com','accounts':['5593295048','5473167378'],
                                  'state':'NOT_VERIFIED'},
            'note':'Gündem ve açık işler ayrı kaynaklardır; her biri son 25 kayıtla sınırlıdır. Birlikte toplam iş sayısı değildir.'}
