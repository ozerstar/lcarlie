"""Read-only organisational checks. No employee scoring or external actions."""
from datetime import datetime, timezone
from .connection_scope import LIMITATIONS


def organisation(rows):
    from . import roster
    departments = rows.get('departments', [])
    staffed = roster.departman_uyeleri()
    empty = [d['kod'] for d in departments if not staffed.get(d.get('kod'))]
    missing = [d['kod'] for d in departments if staffed.get(d.get('kod')) and
               (not roster.departman_sorumlusu(d['kod']) or
                roster.departman_sorumlusu(d['kod']).key not in
                {m.key for m in staffed[d['kod']]})]
    return (f"{len(departments)} departman incelendi. Kadrosuz: {', '.join(empty) or 'yok'}. "
            f"Geçerli ekip sorumlusu eksik: {', '.join(missing) or 'yok'}. "
            "Kadro veya yetki değişikliği yapılmadı.")


def connections(rows):
    deps = rows.get('departments', [])
    absent = [d['kod'] for d in deps if d.get('durum') == 'YOK']
    partial = [d['kod'] for d in deps if d.get('durum') == 'KISMI']
    return (f"Kaynak kaydı bağlı olmayan birimler: {', '.join(absent) or 'yok'}. "
            f"Kısmi bağlantılar: {', '.join(partial) or 'yok'}. "
            "Bu kayıt durumu canlı bağlantı testi değildir; bağlantıyı kullanıcı tamamlamalı.")


def work_review(rows):
    work = rows.get('open_work', [])
    agenda = rows.get('agenda', [])
    return (f"{len(work)} açık iş kaydı ve {len(agenda)} gündem kaydı incelendi. "
            "Kayıtlar eşleştirilmeden toplam iş veya gecikme iddiası üretilmedi. "
            "İş ataması ve kapatma yapılmadı.")


def development(rows):
    proposals = rows.get('own_proposals', [])
    learning = rows.get('learning_loop', [])
    return (f"{len(proposals)} iyileştirme önerisi ve {len(learning)} öğrenme kaydı incelendi. "
            "Kişi performansı puanlanmadı; önerilerin uygulanması ayrıca doğrulanmalıdır.")


SPEAKERS = {'ik_organizasyon': organisation, 'ik_kaynak': connections,
            'ik_is_takibi': work_review, 'ik_gelisim': development}


def review(departments, *, member_error=''):
    """Use the same snapshot as the team panel; never query opinions recursively."""
    from . import roster
    findings = []
    def add(code, kind, title, detail, action):
        findings.append(dict(id=f'{code}:{kind}', department=code, kind=kind,
                             title=title, detail=detail, action=action))
    for d in departments:
        code = d['kod']
        status = d.get('birim_durumu')
        members = d.get('uyeler', [])
        if status == 'YOK':
            add(code, 'source_missing', 'Kaynağı bağlamanız gerekiyor',
                'Departman kaynak kaydı bağlı değil. Üyeler başka şirket kaynaklarını okuyabilir.',
                'Kaynak kaydını ve gerekli hesabı kontrol et; bağlantıyı test et.')
        elif status == 'KISMI':
            add(code, 'source_partial', 'Bağlantı eksiklerini kontrol edin',
                LIMITATIONS.get(code, 'Kısmi bağlantı tanımlı; eksik izin veya kapsam kaynaktan doğrulanmalı.'),
                'Kaynak kapsamını ve son başarılı okumayı incele.')
        elif status not in ('CALISIYOR',):
            add(code, 'source_unknown', 'Kaynak durumu bilinmiyor',
                'Bağlantı kaydı doğrulanamadı.', 'Kaynak kaydını incele.')
        if not members:
            add(code, 'staffing', 'Kadro tanımlı değil',
                'Departman korunur; sahte üye oluşturulmaz.', 'Görev ve veri gereksinimini belirle.')
        else:
            manager = roster.departman_sorumlusu(code)
            if not manager or manager.key not in {m.get('key') for m in members}:
                add(code, 'manager', 'Geçerli ekip sorumlusu eksik',
                    'Sorumlu bu departmanın kadrosunda bulunamadı.', 'Sorumlu eşlemesini gözden geçir.')
        for m in members:
            state = m.get('durum')
            if state != roster.SPEAKS or m.get('eksik'):
                add(code, 'member_' + m['key'], m.get('ad') or m['key'],
                    f"Son ölçüm: {state or 'bilinmiyor'}. Eksik sorgular: {', '.join(m.get('eksik') or []) or 'belirtilmedi'}.",
                    'Üyenin kaynaklarını ve son döngüsünü incele; mola animasyonu faaliyet kanıtı değildir.')
    return dict(generated_at=datetime.now(timezone.utc).isoformat(), findings=findings,
                source_missing=sum(f['kind'] == 'source_missing' for f in findings),
                source_partial=sum(f['kind'] == 'source_partial' for f in findings),
                member_error=member_error, read_only=True)
