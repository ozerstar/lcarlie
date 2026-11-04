import { departmentName } from './labels.js';
// Union both real sources by stable identities. Never invent members for empty rooms.
export function syncDepartments(agentsData, ekipData) {
  const detailed = new Map((ekipData?.departmanlar || []).filter(d => d?.kod).map(d => [d.kod, d]));
  const primary = new Map((agentsData?.departmanlar || []).filter(d => d?.kod).map(d => [d.kod, d]));
  return [...new Set([...primary.keys(), ...detailed.keys()])].map(code => {
    const d = primary.get(code) || {}, extra = detailed.get(code) || {};
    const members = new Map((d.kadro || []).filter(m => m?.key).map(m => [m.key, {...m}]));
    for (const m of extra.uyeler || []) {
      if (!m?.key) continue;
      const old = members.get(m.key) || {};
      members.set(m.key, {...old, key: m.key, name: m.ad ?? old.name,
        job: m.gorev ?? old.job, status: m.durum ?? old.status,
        statement: m.soyledigi ?? old.statement, reads: m.okur ?? old.reads,
        missing: m.eksik || [], sorumlu_mu: old.sorumlu_mu || d.sorumlu?.key === m.key});
    }
    const kadro = [...members.values()];
    return {...d, ...extra, kod: code, ad: departmentName(code,extra.ad || d.ad), original_name: extra.ad || d.ad || code,
      sorumlu: d.sorumlu || null, kadro, kisi: kadro.length};
  }).sort((a,b) => (a.kod === 'EXEC' ? -1 : b.kod === 'EXEC' ? 1 :
    (a.aile || '').localeCompare(b.aile || '', 'tr') || a.ad.localeCompare(b.ad, 'tr')));
}
