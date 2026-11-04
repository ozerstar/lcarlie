"""Editable gift reconciliation; never posts ledger or stock movements."""
import copy
from datetime import datetime, timezone
import cari
from personal_action_store import _connect

def integer(value, label, maximum=10000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise cari.CariError(label + ' sıfır veya pozitif tam sayı olmalı.')
    return value

def recalculate(record):
    r = copy.deepcopy(record)
    extra_discount = integer(r.get('extra_discount_bps', 0), 'Ek iskonto', 10000)
    for p in r['products']:
        initial = integer(p.get('initial_gift_quantity', 0), 'Listedeki hediye adedi', p['initial_quantity'])
        extra = integer(p.get('additional_gift_quantity', 0), 'Ek hediye adedi')
        p['known_gift_quantity'] = initial + extra
        p['return_gift_offset_quantity'] = min(p['return_quantity'], initial + extra)
        p['refundable_return_quantity'] = max(0, p['return_quantity'] - initial - extra)
        discount = integer(p.get('discount_bps', 4000), 'İskonto', 10000)
        psf = p.get('reference_psf_cents')
        base = None if psf is None else (psf * (10000-discount) + 5000) // 10000
        unit = None if base is None else (base * (10000-extra_discount) + 5000) // 10000
        alternative = None if base is None else (base * 9500 + 5000) // 10000
        p['initial_discounted_unit_cents'] = unit
        p['initial_paid_quantity'] = p['initial_quantity'] - initial
        p['initial_estimate_cents'] = 0 if not p['initial_paid_quantity'] else None if unit is None else p['initial_paid_quantity'] * unit
        p['initial_alternative_cents'] = 0 if not p['initial_paid_quantity'] else None if alternative is None else p['initial_paid_quantity'] * alternative
        mode = p.get('return_price_mode', 'fixed' if p.get('additional_unit_price_cents') is not None else 'discounted')
        p['return_price_mode'] = mode
        if mode == 'fixed':
            unit = p.get('fixed_return_unit_cents', p.get('return_unit_estimate_cents'))
            p['fixed_return_unit_cents'] = unit
            alternative = unit
        p['return_unit_estimate_cents'],p['return_alternative_unit_cents'] = unit,alternative
        qty = p['refundable_return_quantity']
        p['return_estimate_cents'] = 0 if not qty else None if unit is None else qty * unit
        p['return_alternative_cents'] = 0 if not qty else None if alternative is None else qty * alternative
    def total(key):
        values = [p[key] for p in r['products']]
        return None if any(v is None for v in values) else sum(values)
    initial_total, alternative_total = total('initial_estimate_cents'),total('initial_alternative_cents')
    extra_rows = [p for p in r['products'] if p['additional_quantity']]
    extra_total = None if any(p['additional_unit_price_cents'] is None for p in extra_rows) else sum(p['additional_quantity'] * p['additional_unit_price_cents'] for p in extra_rows)
    received = lambda group: sum(p['amount_cents'] for p in r['payments'] if p.get('group') == group)
    r['price_comparison'] = {
        'initial_cents': initial_total, 'initial_alternative_cents': alternative_total,
        'initial_received_cents': received('initial'), 'extra_cents': extra_total,
        'extra_received_cents': received('extra'),
        'gap_cents': None if initial_total is None else initial_total - received('initial'),
        'alternative_gap_cents': None if alternative_total is None else alternative_total - received('initial'),
    }
    r['delivery_note'] = 'İlk liste adedi, liste içindeki hediyeleri de içerir. Ek ücretli teslim ve ayrıca verilen hediyeler toplam teslim adedine eklenir. Aynı ürünün bilinen hediyeleri ücretli iade adedinden düşülür.'
    r['estimate_note'] = 'Ön hesaptır. Seçilen ürün iskontosu ve ek iskonto art arda uygulanır. Ek %5 karşılaştırması, seçilen ürün iskontosu sonrasında yalnız %5 uygular; seçili ek iskontoya bir kez daha eklenmez. Ek ücretli teslim fiyatı ve sabit iade fiyatı ayrıca girilir, otomatik iskonto uygulanmaz. Bilinen hediyeler aynı üründen mahsup edilir. Eski PSF referanslarının satış tarihindeki fiyat olduğu doğrulanmadı.'
    r['pending_note'] = 'Değişiklikler mutabakat kaydıdır; kesinleşmiş cari veya stok hareketi oluşturmaz. Fiyatlar, diğer hediyeler ve işlem tarihleri doğrulanmayı bekliyor. Fiziksel iade teslimi doğrulanmadı.'
    return r

def apply_full_edit(record, body):
    revision = integer(body.get('revision'), 'Kayıt sürümü', 1000000)
    if revision != record.get('revision', 0):
        raise cari.CariConflict('Mutabakat başka bir yerde değişti. Sayfayı yenileyip yeniden deneyin.')
    edits = body.get('products')
    if not isinstance(edits, list) or len(edits)>200:
        raise cari.CariError('En fazla 200 ürün düzenlenebilir.')
    r=copy.deepcopy(record);known={p['sku']:p for p in r['products']};result=[];seen=set()
    for item in edits:
        if not isinstance(item,dict):raise cari.CariError('Ürün satırı geçersiz.')
        sku=cari._text(item.get('sku'), 'Ürün kimliği', 160, True)
        if sku in seen:raise cari.CariError('Aynı ürün iki satırda gönderilemez.')
        seen.add(sku)
        p=copy.deepcopy(known.get(sku,{}))
        p['sku']=sku;p['name']=cari._text(item.get('name'), 'Ürün adı', 160, True)
        for key in ('initial_quantity','additional_quantity','return_quantity','additional_gift_quantity'):
            p[key]=integer(item.get(key), 'Ürün veya hediye adedi')
        p['initial_gift_quantity']=integer(item.get('initial_gift_quantity'),'Liste içindeki hediye',p['initial_quantity'])
        p['discount_bps']=integer(item.get('discount_bps'), 'İskonto',10000)
        for key in ('reference_psf_cents','additional_unit_price_cents','fixed_return_unit_cents'):
            p[key]=None if item.get(key) is None else integer(item[key],'Birim fiyat',1000000000)
        p['return_price_mode']=item.get('return_price_mode')
        if p['return_price_mode'] not in ('fixed','discounted'):raise cari.CariError('İade fiyat yöntemi geçersiz.')
        result.append(p)
    r['products']=result;r['extra_discount_bps']=integer(body.get('extra_discount_bps'), 'Ek iskonto',10000)
    r=recalculate(r);r['revision']=revision+1;r['updated_at']=datetime.now(timezone.utc).isoformat()
    return r

def apply_edit(record, body):
    revision = integer(body.get('revision'), 'Kayıt sürümü', 1000000)
    if revision != record.get('revision', 0):
        raise cari.CariConflict('Bu mutabakat başka bir yerde değiştirildi. Sayfayı yenileyip yeniden deneyin.')
    edits = body.get('products')
    if not isinstance(edits, list) or len(edits) != len(record['products']):
        raise cari.CariError('Bütün ürünlerin hediye adetleri birlikte gönderilmeli.')
    known = {p['sku']: p for p in record['products']}
    if any(not isinstance(p, dict) or not isinstance(p.get('sku'), str) for p in edits):
        raise cari.CariError('Ürün bilgileri geçersiz.')
    if len({p['sku'] for p in edits}) != len(edits) or {p['sku'] for p in edits} != set(known):
        raise cari.CariError('Ürünler değişmiş; sayfayı yenileyin.')
    r = copy.deepcopy(record)
    by_sku = {p['sku']: p for p in r['products']}
    for item in edits:
        p = by_sku[item['sku']]
        p['initial_gift_quantity'] = integer(item.get('initial_gift_quantity'), 'Listedeki hediye adedi', p['initial_quantity'])
        p['additional_gift_quantity'] = integer(item.get('additional_gift_quantity'), 'Ek hediye adedi')
    r = recalculate(r)
    r['revision'] = revision + 1
    r['updated_at'] = datetime.now(timezone.utc).isoformat()
    return r

def update(owner, body):
    account = cari._id(body.get('account_id'))
    identifier = cari._id(body.get('document_id'))
    request_id = cari._text(body.get('request_id'), 'İstek kimliği', 100, True)
    if len(request_id) < 16:
        raise cari.CariError('İstek kimliği geçersiz.')
    digest = cari._digest(body)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (owner + ':' + account,))
        cur.execute("SELECT extracted FROM core.jarvis_cari_document WHERE owner=%s AND account_id=%s AND document_id=%s AND source='attachment' FOR UPDATE", (owner, account, identifier))
        row = cur.fetchone()
        if row is None:
            raise cari.CariNotFound('Bu cariye ait mutabakat bulunamadı.')
        extracted = row['extracted']
        record = extracted.get('cari_reconciliation', {})
        if record.get('version') != 1 or record.get('status') != 'pending':
            raise cari.CariConflict('Bu mutabakat artık düzenlenebilir durumda değil.')
        audit = extracted.get('reconciliation_audit', [])
        for event in audit:
            if event['request_id'] == request_id:
                if event['digest'] != digest:
                    raise cari.CariConflict('Aynı istek kimliği farklı değişiklik için kullanılamaz.')
                return {'saved': True, 'reused': True, 'revision': record.get('revision', 0)}
        updated = apply_full_edit(record, body) if body.get('mode') == 'full' else apply_edit(record, body)
        gifts = lambda r: [{k: p.get(k, 0) for k in ('sku', 'initial_gift_quantity', 'additional_gift_quantity')} for p in r['products']]  # noqa: F841
        audit.append({'request_id': request_id, 'digest': digest, 'actor': owner, 'at': updated['updated_at'], 'before': record, 'after': updated})
        extracted.update(cari_reconciliation=updated, reconciliation_audit=audit)
        cur.execute('UPDATE core.jarvis_cari_document SET extracted=%s,updated_at=clock_timestamp() WHERE owner=%s AND account_id=%s AND document_id=%s', (Jsonb(extracted), owner, account, identifier))
    return {'saved': True, 'revision': updated['revision']}
