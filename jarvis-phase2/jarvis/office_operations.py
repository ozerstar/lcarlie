"""Source-backed office boards and auditable, local follow-ups.

An office follow-up never closes or changes the upstream business record.
Limited query disappearance is not evidence of resolution.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from .display_language import display

QUERIES = ('departments', 'open_work', 'agenda', 'urun_karti', 'ecommerce_profitability', 'provenance', 'decision_outcomes')
_lock = threading.Lock()
_cache = {}

def now():
    return datetime.now(timezone.utc).isoformat()

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:24]

def unique_index(rows, key):
    groups = {}
    for r in rows:
        v = str(r.get(key) or '').strip()
        if v:
            groups.setdefault(v, []).append(r)
    return {k: v[0] for k, v in groups.items() if len(v) == 1}

def products(rows, catalog):
    cards = rows.get('urun_karti', [])
    profits = unique_index(rows.get('ecommerce_profitability', []), 'entity_id')
    images = unique_index(catalog.get('urunler', []), 'sku')
    card_skus = unique_index(cards, 'sku')
    result = []
    for r in cards:
        ident = str(r.get('urun_id') or r.get('entity_id') or '')
        sku = str(r.get('sku') or '')
        c = images.get(sku, {}) if sku in card_skus else {}
        files = [f for f in c.get('gorseller', []) if isinstance(f, str) and re.fullmatch(r'[a-zA-Z0-9.-]+\.(?:webp|png|jpg|jpeg)', f)]
        p = profits.get(ident, {})
        result.append(dict(id=ident, name=display(r.get('urun_adi')), image='/katalog-gorsel/'+files[0] if files else None,
                           website_price=r.get('wix_satis'), website_stock=r.get('wix_stok'), published=r.get('wix_yayinda'),
                           marketplace_price=r.get('trendyol_satis'), marketplace_stock=r.get('trendyol_stok'),
                           cost=r.get('birim_maliyet'), cost_source={'ELLE':'Elle girilmiş maliyet'}.get(r.get('maliyet_kaynagi'), display(r.get('maliyet_kaynagi') or 'Kaynak belirtilmemiş')),
                           net_revenue=p.get('ciro_net'), gross_margin=p.get('brut_marj_yuzde'), coverage=p.get('kapsama_yuzde'),
                           note='Brüt marj kaynak kaydıdır; doğrulanmış net kâr değildir. Dönem bilgisi bu okumada bulunmuyor.',
                           image_date=catalog.get('uretim_at')))
    return result

class Conflict(ValueError):
    pass

class Store:
    def __init__(self, directory):
        self.path = Path(directory) / 'office-work.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS followups(id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS audits(id INTEGER PRIMARY KEY, item TEXT, actor TEXT, at TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS checks(department TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notices(actor TEXT, item TEXT, fingerprint TEXT, PRIMARY KEY(actor,item));
            CREATE TABLE IF NOT EXISTS observations(member TEXT, cycle TEXT, status TEXT, PRIMARY KEY(member,cycle));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def all(self):
        with self.connect() as db:
            return {r[0]: dict(json.loads(r[1]), version=r[2]) for r in db.execute('SELECT id,payload,version FROM followups')}

    def checks(self):
        with self.connect() as db:
            return {r[0]: json.loads(r[1]) for r in db.execute('SELECT department,payload FROM checks')}

    def acknowledge(self, actor, ident, digest):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO notices VALUES(?,?,?)', (actor, ident, digest))

    def acknowledged(self, actor):
        with self.connect() as db:
            return dict(db.execute('SELECT item,fingerprint FROM notices WHERE actor=?', (actor,)))

    def save(self, body, actor, items, members):
        ident = str(body.get('id', ''))
        original = next((i for i in items if i['id'] == ident), None)
        if original is None:
            raise ValueError('İş kaydı bulunamadı. Listeyi yenileyin.')
        department = str(body.get('department', ''))
        owner = str(body.get('owner', ''))
        if department not in members:
            raise ValueError('Geçerli bir birim seçin.')
        if owner and owner not in {m.key for m in members[department]}:
            raise ValueError('Sorumlu, seçilen birimin kadrosunda bulunmalıdır.')
        due = str(body.get('due') or '')
        if due:
            try:
                if date.fromisoformat(due).isoformat() != due:
                    raise ValueError()
            except ValueError:
                raise ValueError('Teslim tarihini geçerli bir gün olarak seçin.') from None
        status = body.get('status', 'open')
        if status not in ('open', 'progress', 'blocked', 'resolved'):
            raise ValueError('Geçerli bir çözüm durumu seçin.')
        note = str(body.get('note') or '').strip()[:1500]
        if status == 'resolved' and not note:
            raise ValueError('Takibi kapatmak için çözüm açıklaması yazın.')
        try:
            version = int(body.get('version', 0))
        except (TypeError, ValueError):
            raise ValueError('Kayıt sürümü geçersiz. Listeyi yenileyin.') from None
        payload = dict(original, department=department, owner=owner, due=due, status=status, note=note, updated_at=now())
        payload.pop('version', None)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT version FROM followups WHERE id=?', (ident,)).fetchone()
            if (old[0] if old else 0) != version:
                raise Conflict('Bu kayıt başka bir oturumda değişti. Listeyi yenileyip yeniden deneyin.')
            db.execute('INSERT OR REPLACE INTO followups VALUES(?,?,?)', (ident, json.dumps(payload, ensure_ascii=False), version+1))
            db.execute('INSERT INTO audits(item,actor,at,payload) VALUES(?,?,?,?)', (ident, actor, now(), json.dumps(payload, ensure_ascii=False)))
        return dict(payload, version=version+1)

    def observe(self, report):
        cycle = str(report.get('generated_at') or '')
        if not cycle:
            return {}
        with self.connect() as db:
            for key, value in report.get('activity', {}).items():
                db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?)', (key, cycle, str(value.get('status', ''))))
            # Retain a bounded recent history, independent of refresh frequency.
            db.execute('DELETE FROM observations WHERE cycle NOT IN (SELECT DISTINCT cycle FROM observations ORDER BY cycle DESC LIMIT 30)')
            history = list(db.execute('SELECT member,cycle,status FROM observations ORDER BY cycle DESC'))
        seen = {}
        for member, _, status in history:
            seen.setdefault(member, []).append(status)
        return {k: sum(s == 'ERROR' for s in v[:3]) for k, v in seen.items() if len(v) >= 2 and v[0] == 'ERROR' and v[1] == 'ERROR'}

def read_snapshot(memory):
    with _lock:
        if _cache.get('memory') is memory and time.monotonic()-_cache.get('time', 0) < 60:
            return _cache['value']
        rows, reads = {}, {}
        for query in QUERIES:
            try:
                e = memory._fetch(query)
                rows[query] = list(e.records)
                reads[query] = dict(ok=True, source=e.source, at=now(), count=len(e.records))
            except Exception:  # noqa: BLE001
                rows[query] = []
                reads[query] = dict(ok=False, source=query, at=now(), note='Kaynak okunamadı; boş kayıt olduğu sonucu çıkarılamaz.')
        value = (rows, reads)
        _cache.update(memory=memory, time=time.monotonic(), value=value)
        return value

def snapshot(memory, directory, actor='', catalog=None, report=None):
    from . import roster
    rows, reads = read_snapshot(memory)
    store = Store(directory)
    members = roster.departman_uyeleri()
    checks = store.checks()
    acknowledgements = store.acknowledged(actor)
    items, connections = [], []
    def add(identity, title, detail, department='', source='', kind='work', action=''):
        item = dict(id=fingerprint(identity), title=display(title), detail=display(detail), department=department,
                    source=display(source), kind=kind, action=display(action), owner='', due='', status='open', version=0)
        item['fingerprint'] = fingerprint([title, detail, action])
        items.append(item)
    for d in rows['departments']:
        code = d['kod']
        source = display(d.get('veri_kaynagi') or 'Kaynak belirtilmemiş')
        state = {'YOK': 'Kaynak bağlı değil', 'KISMI': 'Kısmi bağlantı', 'CALISIYOR': 'Kaynak tanımlı'}.get(d.get('durum'), 'Durum doğrulanmadı')
        action = ('Google Ads hesap seçimi ertelendi. Hazır olduğunuzda iki reklam hesabını seçip bağlantıyı tamamlayın.' if code == 'GOOGLE_ADS' else
                  'Kaynak kaydındaki hesap ve izin kapsamını kontrol edin; ardından okuma denetimini çalıştırın.')
        connections.append(dict(department=code, name=display(d['ad']), source=source, state=state,
                                permission='Gerekli izin kapsamı bu kayıtta belirtilmemiş.', action=action, check=checks.get(code),
                                reads=[display(q) for q in dict.fromkeys(q for m in members.get(code, ()) for q in m.reads)]))
        if d.get('durum') != 'CALISIYOR':
            add(['source', code], d['ad']+' · '+state, source, code, 'Departman kaynak kaydı', 'source', action)
        if not members.get(code):
            add(['staff', code], d['ad']+' · Kadro eksik', 'Bu birime henüz üye atanmamış.', code, 'Şirket kadrosu', 'staff')
    for r in rows['open_work']:
        add(['work', r.get('tur'), r.get('anahtar')], r.get('detay') or 'Açık iş', r.get('yapilacak') or 'Sonraki adım belirtilmemiş.', source='Açık işler', action=r.get('yapilacak') or '')
    for r in rows['agenda']:
        code = str(r.get('hedef') or '')
        add(['agenda', r.get('soru_id')], r.get('soru') or 'Şirket gündemi', r.get('neden_onemli') or '', code if code in members else '', 'Şirket gündemi', 'agenda', r.get('kaynak_plani') or '')
    repeated = store.observe(report or {})
    for code, team in members.items():
        for m in team:
            if m.key in repeated:
                add(['failure', m.key], m.name+' · Tekrarlayan işlem hatası', 'Arka arkaya en az iki ayrı ekip döngüsünde hata kaydı var.', code, 'Ekip döngüsü', 'failure', 'Üyenin kaynaklarını ve işlem kaydını inceleyin.')
    saved = store.all()
    current = {i['id']: i for i in items}
    for ident, item in current.items():
        if ident in saved:
            patch = saved[ident]
            for key in ('department', 'owner', 'due', 'status', 'note', 'updated_at', 'version'):
                item[key] = patch.get(key, item.get(key))
        item['observed'] = True
    for ident, item in saved.items():
        if ident not in current:
            current[ident] = dict(item, observed=False)
    today = datetime.now().astimezone().date().isoformat()
    for item in current.values():
        item['overdue'] = bool(item.get('due') and item['due'] < today and item['status'] != 'resolved')
        item['new'] = acknowledgements.get(item['id']) != item['fingerprint']
        item['issues'] = ([] if item.get('owner') else ['Sorumlu atanmamış']) + ([] if item.get('due') else ['Teslim tarihi belirlenmemiş'])
        if item['overdue']:
            item['issues'].append('Teslim tarihi geçmiş')
    # Only explicit duplicate work identities assigned to different owners count as a conflict.
    assignments = {}
    for item in current.values():
        if item.get('owner') and item['status'] != 'resolved':
            assignments.setdefault((item['source'], item['title']), []).append(item)
    for group in assignments.values():
        if len({i['owner'] for i in group}) > 1:
            for item in group:
                item['issues'].append('Aynı kaynak ve başlıkta farklı sorumlular var; görev paylaşımını kontrol edin')
    return dict(generated_at=now(), items=list(current.values()), connections=connections, products=products(rows, catalog or {}),
                reads=reads, provenance=rows['provenance'], decisions=rows['decision_outcomes'],
                members={k: [dict(key=m.key, name=m.name) for m in v] for k, v in members.items()},
                limits='Açık işler ve gündem ayrı ayrı en son 25 kayıtla sınırlıdır. Karar listesi en son 200 kayıtla sınırlıdır. Listede görünmemek tamamlandığı anlamına gelmez. Takip kaydını kapatmak kaynak işi kapatmaz.')

def check_source(memory, directory, code):
    from . import roster
    members = roster.departman_uyeleri()
    if code not in members:
        raise ValueError('Birim kadrosu bulunamadı. Önce sorumlu ve kaynak tanımlayın.')
    queries = list(dict.fromkeys(q for m in members[code] for q in m.reads))
    results = []
    for q in queries:
        try:
            e = memory._fetch(q)
            results.append(dict(name=display(q), ok=True, count=len(e.records), at=str(e.retrieved_at)))
        except Exception:  # noqa: BLE001
            results.append(dict(name=display(q), ok=False, at=now()))
    store = Store(directory)
    old = store.checks().get(code, {})
    success = bool(results) and all(r['ok'] for r in results)
    value = dict(at=now(), ok=success, last_success=now() if success else old.get('last_success'), results=results,
                 note='Bu denetim ekip sorgularının okunabildiğini sınar. Dış hesabın tüm izinlerini veya verinin güncelliğini doğrulamaz.')
    with store.connect() as db:
        db.execute('INSERT OR REPLACE INTO checks VALUES(?,?)', (code, json.dumps(value, ensure_ascii=False)))
    return value
