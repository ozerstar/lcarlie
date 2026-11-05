"""Recover team tasks retained in the improvement ledger but pruned from the queue.

Recovery never claims that an unknown task was completed. The original work ID,
objective, owner and due date remain intact; a recovered task must be replanned
before a worker can execute it.
"""
from __future__ import annotations

from .is_uretici import Agac


def recover_pruned_work(store, tree_dir, now):
    tree = Agac(tree_dir)
    data = tree.oku()
    existing = {task.get('work_id') for dep in data['departmanlar'].values()
                for task in dep.get('gorevler', [])}
    with store.db() as db:
        works = [dict(row) for row in db.execute(
            "SELECT id,source_key,domain,objective,owner,metric,unit,target,due,created,source "
            "FROM work WHERE source_key LIKE 'isuretici:%' ORDER BY id")]
    recovered = 0
    for work in works:
        if work['id'] in existing:
            continue
        task_id = work['source_key'][len('isuretici:'):]
        domain = work['domain'].split(' · ', 1)
        code = domain[0]
        title, _, output = work['objective'].partition(' — Teslim: ')
        dep = data['departmanlar'].setdefault(code, {
            'ad': domain[1] if len(domain) > 1 else code,
            'gorevler': [], 'raporlar': [], 'fikirler': []})
        dep['gorevler'].append({
            'id': task_id, 'work_id': work['id'], 'baslik': title,
            'tip': 'BELIRSIZ', 'sorumlu': work['owner'],
            'cikti': output or 'Teslim türü yeniden doğrulanacak',
            'kabul_olcutu': work['metric'].removeprefix('Kabul: '),
            'olusturma': work['created'], 'son_tarih': work['due'],
            'kaynak': work['source'], 'durum': 'YENIDEN_PLANLA',
            'neden': 'Görev ağacından budanmış; iyileştirme defterinden geri alındı.',
        })
        existing.add(work['id'])
        recovered += 1
    if recovered:
        tree.yaz(data, now)
    return recovered
