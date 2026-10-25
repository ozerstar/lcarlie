"""Owner-scoped order/invoice observations. No provider calls or ledger posting.

Connectors must map verified provider fields to this canonical envelope.
An order, a shipment and a POS payment remain distinct observations. They
are joined only by an explicit channel/store/order identifier, never by name.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

import cari
from personal_action_store import _connect

SOURCES = {
    'trendyol': ('Trendyol', 'order'), 'n11': ('n11', 'order'),
    'amazon': ('Amazon', 'order'), 'hepsiburada': ('Hepsiburada', 'order'),
    'wix': ('Wix', 'order'), 'basitkargo': ('BasitKargo', 'shipment'),
    'qnb_pos': ('QNB POS', 'pos_payment'),
}
ORDER_SOURCES = frozenset(k for k, v in SOURCES.items() if v[1] == 'order')
INVOICE_LABELS = {'unknown': 'Fatura bilgisi doğrulanmadı', 'missing': 'Fatura eksik',
                  'draft': 'Fatura taslak', 'issued': 'Fatura düzenlenmiş',
                  'cancelled': 'Fatura iptal edilmiş'}
STATUSES = {
    'order': frozenset({'unknown', 'pending', 'processing', 'shipped', 'delivered', 'cancelled', 'returned'}),
    'shipment': frozenset({'unknown', 'pending', 'in_transit', 'delivered', 'cancelled', 'returned'}),
    'pos_payment': frozenset({'unknown', 'pending', 'approved', 'declined', 'voided', 'refunded'}),
}


def _text(body, key, limit=160, required=False):
    return cari._text(body.get(key, ''), key, limit, required)


def _time(value):
    if not isinstance(value, str) or len(value) > 40:
        raise cari.CariError('Kaynak güncelleme tarihi gerekli.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise cari.CariError('Kaynak tarihi ISO 8601 biçiminde olmalı.') from exc
    if parsed.tzinfo is None:
        raise cari.CariError('Kaynak tarihinde saat dilimi gerekli.')
    return parsed.astimezone(timezone.utc).isoformat()


def normalize(body):
    if (not isinstance(body, dict) or not isinstance(body.get('source'), str)
            or body['source'] not in SOURCES):
        raise cari.CariError('Kaynak geçersiz.')
    source = body['source']
    object_type = SOURCES[source][1]
    status = body.get('status', 'unknown')
    if not isinstance(status, str) or status not in STATUSES[object_type]:
        raise cari.CariError('Kaynak durumu geçersiz.')
    currency = body.get('currency')
    if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
        raise cari.CariError('Para birimi açıkça girilmeli.')
    result = {
        'source': source, 'object_type': object_type,
        'store_id': _text(body, 'store_id', required=True),
        'store_name': _text(body, 'store_name'),
        'object_id': _text(body, 'object_id', required=True),
        'source_updated_at': _time(body.get('source_updated_at')),
        'customer_name': _text(body, 'customer_name'),
        'customer_id': _text(body, 'customer_id'),
        'status': status, 'currency': currency,
        'gross_cents': None if body.get('gross_amount') is None else
                       cari._money(body['gross_amount'], 'Brüt tutar'),
        'payment_status': body.get('payment_status', 'unknown'),
        'invoice': None, 'order_link': None,
        'account_id': body.get('account_id') or None,
        'evidence_kind': body.get('evidence_kind', 'manual'),
    }
    if not isinstance(result['evidence_kind'], str) or result['evidence_kind'] not in ('manual', 'provider_api', 'provider_export'):
        raise cari.CariError('Kayıt kaynağı türü geçersiz.')
    if not isinstance(result['payment_status'], str) or result['payment_status'] not in ('unknown', 'pending', 'partial', 'paid', 'refunded'):
        raise cari.CariError('Ödeme durumu geçersiz.')
    if result['account_id'] is not None:
        cari._id(result['account_id'])
    invoice = body.get('invoice')
    if object_type == 'order':
        if invoice is None:
            invoice = {}
        if (not isinstance(invoice, dict) or not isinstance(invoice.get('status', 'unknown'), str)
                or invoice.get('status', 'unknown') not in INVOICE_LABELS):
            raise cari.CariError('Fatura bilgileri geçersiz.')
        result['invoice'] = {
            'status': invoice.get('status', 'unknown'),
            'number': _text(invoice, 'number', 100),
            'uuid': _text(invoice, 'uuid', 100),
            'gross_cents': None if invoice.get('gross_amount') is None else
                           cari._money(invoice['gross_amount'], 'Fatura tutarı'),
            'provider': _text(invoice, 'provider', 100),
            'platform_status': invoice.get('platform_status', 'unknown'),
        }
        if (not isinstance(result['invoice']['platform_status'], str) or
                result['invoice']['platform_status'] not in ('unknown','pending','uploaded','rejected','not_applicable')):
            raise cari.CariError('Platform fatura aktarım durumu geçersiz.')
        if result['invoice']['status'] == 'issued' and not (
                result['invoice']['number'] or result['invoice']['uuid']):
            raise cari.CariError('Düzenlenmiş fatura için numara veya belge kimliği gerekli.')
        if body.get('order_link') is not None:
            raise cari.CariError('Sipariş kendisi başka siparişe bağlanamaz.')
    else:
        if invoice is not None:
            raise cari.CariError('Kargo veya POS kaydı sipariş faturası sayılmaz.')
        link = body.get('order_link')
        if link is not None:
            if (not isinstance(link, dict) or not isinstance(link.get('source'), str)
                    or link.get('source') not in ORDER_SOURCES):
                raise cari.CariError('Sipariş bağlantısı geçersiz.')
            result['order_link'] = {'source': link['source'],
                'store_id': _text(link, 'store_id', required=True),
                'object_id': _text(link, 'object_id', required=True)}
    return result


def observe(owner, body):
    payload = normalize(body)
    event_key = _text(body, 'event_key', 160, required=True)
    digest = cari._digest(payload)
    from psycopg.types.json import Jsonb
    lock_key = json.dumps([owner, payload['source'], payload['store_id'], payload['object_id']])
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (lock_key,))
        cur.execute('''SELECT event_id,payload_hash FROM core.jarvis_cari_source_event
            WHERE owner=%s AND source=%s AND store_id=%s AND event_key=%s''',
            (owner, payload['source'], payload['store_id'], event_key))
        previous = cur.fetchone()
        if previous:
            if previous['payload_hash'] != digest:
                raise cari.CariConflict('Kaynak olay kimliği farklı içerikle tekrar kullanılmış.')
            return {'id': previous['event_id'], 'reused': True}
        if payload['account_id']:
            cur.execute('''SELECT account_id FROM core.jarvis_cari_account
                WHERE owner=%s AND account_id=%s''', (owner, payload['account_id']))
            if cur.fetchone() is None:
                raise cari.CariNotFound('Bağlanacak cari bulunamadı.')
        identifier = uuid.uuid4().hex
        cur.execute('''INSERT INTO core.jarvis_cari_source_event
            (event_id,owner,source,store_id,object_id,event_key,source_updated_at,payload_hash,payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (identifier, owner, payload['source'], payload['store_id'], payload['object_id'],
             event_key, payload['source_updated_at'], digest, Jsonb(payload)))
    return {'id': identifier, 'reused': False}


def board(owner):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT DISTINCT ON (source,store_id,object_id)
            event_id,payload,created_at FROM core.jarvis_cari_source_event
            WHERE owner=%s ORDER BY source,store_id,object_id,source_updated_at DESC,
                created_at DESC,event_id DESC''', (owner,))
        rows = cur.fetchall()
    return project(rows)


def project(rows):
    channels = {key: {'id': key, 'name': value[0], 'kind': value[1], 'records': 0,
                     'store_ids': set(), 'last_received_at': None,
                     'live_connection_verified': False} for key, value in SOURCES.items()}
    orders, other = [], []
    index = {}
    for row in rows:
        p = row['payload']
        channel = channels[p['source']]
        channel['records'] += 1
        channel['store_ids'].add(p['store_id'])
        received = str(row['created_at'])
        if channel['last_received_at'] is None or received > channel['last_received_at']:
            channel['last_received_at'] = received
        item = dict(p, observation_id=row['event_id'], received_at=received, related=[])
        if p['object_type'] == 'order':
            inv = p['invoice']
            issues = []
            if p['status'] not in ('cancelled', 'returned'):
                if inv['status'] in ('missing', 'unknown', 'draft', 'cancelled'):
                    issues.append(INVOICE_LABELS[inv['status']])
                if (p['gross_cents'] is not None and inv['gross_cents'] is not None
                        and inv['gross_cents'] != p['gross_cents']):
                    issues.append('Sipariş ve fatura tutarı farklı; belge kapsamını kontrol edin.')
                if inv['platform_status'] in ('pending', 'rejected'):
                    issues.append('Platforma fatura aktarımı bekliyor veya reddedilmiş; kontrol edin.')
            elif inv['status'] == 'issued':
                issues.append('İptal/iade siparişi için fatura ve iade belgesi mutabakatını kontrol edin.')
            item['invoice_checks'] = issues
            orders.append(item)
            index[(p['source'], p['store_id'], p['object_id'])] = item
        else:
            other.append(item)
    for item in other:
        link = item['order_link']
        target = index.get((link['source'], link['store_id'], link['object_id'])) if link else None
        item['order_matched'] = target is not None
        if target is not None:
            target['related'].append({'source': item['source'], 'object_id': item['object_id'],
                                      'status': item['status']})
    cards = []
    for channel in channels.values():
        channel['store_count'] = len(channel.pop('store_ids'))
        cards.append(channel)
    orders.sort(key=lambda p: (not bool(p['invoice_checks']), p['source'], p['store_id'], p['object_id']))
    return {'channels': cards, 'orders': orders, 'other_records': other,
            'invoice_check_count': sum(bool(p['invoice_checks']) for p in orders),
            'order_count': len(orders),
            'notice': 'Kaynak kayıtları fatura kontrolü içindir. Cari bakiyeye veya ciroya otomatik satış eklenmez. Canlı bağlantı durumu bu kayıtlarla doğrulanmaz.'}
