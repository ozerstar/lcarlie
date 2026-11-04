(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const SCOPES = ['lemos', 'moy', 'lcarlie', 'kisisel', 'aile', 'none'];  // fixed order = validated colour order
  const MIX = ['c1', 'c2', 'c3', 'c4', 'c5'];  // fixed categorical order, never cycled; 6th = "other"
  const WEEKDAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
  const state = {csrf: '', view: 'month', book: 'kisisel', scope: '', account: '', category: '', data: null, sort: 'tx_date', asc: false, rows: matchMedia('(max-width: 640px)').matches ? 20 : 60};  // a phone shows cards, not rows
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const tl = (cents, digits = 0) => (Number(cents || 0) / 100).toLocaleString('tr-TR', {minimumFractionDigits: digits, maximumFractionDigits: digits}) + ' ₺';
  const tl2 = cents => tl(cents, 2);
  const short = cents => {
    const v = Math.abs(Number(cents || 0) / 100);
    if (v >= 1e6) return (v / 1e6).toLocaleString('tr-TR', {maximumFractionDigits: 1}) + ' mn';
    if (v >= 1e3) return (v / 1e3).toLocaleString('tr-TR', {maximumFractionDigits: v >= 1e4 ? 0 : 1}) + ' bin';
    return v.toLocaleString('tr-TR', {maximumFractionDigits: 0});
  };
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const parse = s => new Date(s + 'T12:00:00');
  const dayLabel = s => parse(s).toLocaleDateString('tr-TR', {day: 'numeric', month: 'short'});
  const longDay = s => parse(s).toLocaleDateString('tr-TR', {day: 'numeric', month: 'long', year: 'numeric', weekday: 'long'});
  const monthLabel = (s, fmt = 'short') => new Date(s + '-15T12:00:00').toLocaleDateString('tr-TR', {month: fmt, year: fmt === 'long' ? 'numeric' : undefined});
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Istanbul'}).format(new Date());
  // shown and editable everywhere, counted nowhere (owner: "o ayki harcama kaleminden çıkartabilmeliyim")
  const NOT_COUNTED = ['ic_transfer', 'aracilik', 'haric'];
  const uncounted = () => Object.fromEntries(NOT_COUNTED.map(k => [k, state.data.categories[k]]));
  const catMap = dir => ({...(dir === 'in' ? state.data.in_categories : state.data.out_categories), ...uncounted()});

  function error(m) {$('error').textContent = m; $('error').hidden = !m;}
  async function api(url, body) {
    const r = await fetch(url, {credentials: 'same-origin', cache: 'no-store',
      ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf}, body: JSON.stringify(body)})});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'İşlem tamamlanamadı.');
    return d;
  }
  function svg(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }
  function frame(host, height) {
    host.textContent = '';
    const width = Math.max(260, Math.round(host.getBoundingClientRect().width));
    const root = svg('svg', {viewBox: `0 0 ${width} ${height}`, width, height}, host);
    return {root, width, height};
  }
  // round axis: step from 1/2/2.5/5 × 10^n so labels read 50 bin, 100 bin, 150 bin
  function niceScale(v, ticks = 4) {
    if (v <= 0) return {top: ticks, n: ticks};
    const raw = v / ticks, p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * p).find(s => s >= raw);
    return {top: Math.ceil(v / step) * step, n: Math.ceil(v / step)};
  }
  const niceMax = v => niceScale(v).top;
  // a bar whose data end (top) is rounded 4px and whose baseline end stays square
  function barPath(x, y, w, h, r = 4) {
    r = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  function yAxis(g, left, right, top, plotH, max, wanted = 4) {
    const ticks = niceScale(max, wanted).n;
    for (let i = 0; i <= ticks; i++) {
      const v = max / ticks * i, y = top + plotH - plotH * i / ticks;
      svg('line', {x1: left, x2: right, y1: y, y2: y, class: i ? '' : 'base'}, g);
      svg('text', {x: left - 8, y: y + 4, 'text-anchor': 'end'}, g).textContent = short(v);
    }
  }
  const tip = {
    show(html, x, y) {const t = $('tooltip'); t.innerHTML = html; t.hidden = false; t.style.left = Math.min(Math.max(x, 140), innerWidth - 140) + 'px'; t.style.top = Math.max(y, 70) + 'px';},
    hide() {$('tooltip').hidden = true;},
  };
  function hover(node, html, anchor) {
    const at = () => {const b = (anchor || node).getBoundingClientRect(); return [b.left + b.width / 2, b.top];};
    node.addEventListener('mouseenter', () => tip.show(html(), ...at()));
    node.addEventListener('mouseleave', tip.hide);
    node.addEventListener('focus', () => tip.show(html(), ...at()));
    node.addEventListener('blur', tip.hide);
  }
  function change(cur, prev, invert = false) {
    if (!prev) return '<span class="chg">önceki dönemde kayıt yok</span>';
    const pct = (cur - prev) / prev * 100, up = pct > 0;
    const bad = invert ? !up : up;  // for spending, up is bad; for income, up is good
    return `<span class="chg ${Math.abs(pct) < 1 ? '' : bad ? 'up' : 'down'}">${up ? '▲' : '▼'} %${Math.abs(pct).toLocaleString('tr-TR', {maximumFractionDigits: 0})}</span>`;
  }



  // ------------------------------------------------------------ money flow
  // income items → total → spending items (+ what was kept); every node opens its detail
  function renderSankey(r) {
    const host = $('sankey');
    const incomes = r.in_by_category.map(c => ({key: c.key || '__none', label: c.label, total: c.total}));
    const spends = r.by_category.map(c => ({key: c.key || '__none', label: c.label, total: c.total}));
    const inTotal = r.in_total, outTotal = r.out_total;
    if (!inTotal && !outTotal) {host.innerHTML = '<p class="fx-empty">Bu dönemde hareket yok.</p>'; return;}
    if (outTotal > inTotal) incomes.push({key: '__savings', label: 'Birikimden / önceki bakiyeden', total: outTotal - inTotal, synthetic: true});
    let right = spends.slice(0, 7);
    const rest = spends.slice(7);
    if (rest.length) right.push({key: '__rest', label: `Diğer ${rest.length} kalem`, total: rest.reduce((s, c) => s + c.total, 0), items: rest});
    if (inTotal > outTotal) right.push({key: '__kept', label: 'Kenarda kalan', total: inTotal - outTotal, synthetic: true});
    const total = Math.max(inTotal, outTotal);
    // band thickness is proportional; each node also gets at least one label's height so names never overlap
    const thick = 260, scale = thick / total, gap = 6, nodeW = 12, top = 12, minSlot = 34;
    function stack(items) {
      let y = top;
      return items.map(it => {const h = Math.max(2, it.total * scale); const slot = Math.max(h, minSlot); const node = {...it, y: y + (slot - h) / 2, h, slot, end: y + slot}; y += slot + gap; return node;});
    }
    const L = stack(incomes), R = stack(right);
    const sideH = side => side.length ? side.at(-1).end + top + 16 : 0;  // +16: room for the total label
    const height = Math.max(thick + top * 2, sideH(L), sideH(R));
    const {root, width} = frame(host, height);
    const colL = 190, colM = width / 2 - nodeW / 2, colR = width - 210;
    const midH = total * scale, midY = (height - midH) / 2;
    const band = (x1, y1a, y1b, x2, y2a, y2b, cls, title) => {
      const cx = (x1 + x2) / 2;
      const p = svg('path', {d: `M${x1},${y1a} C${cx},${y1a} ${cx},${y2a} ${x2},${y2a} L${x2},${y2b} C${cx},${y2b} ${cx},${y1b} ${x1},${y1b} Z`, class: cls}, root);
      svg('title', {}, p).textContent = title;
      return p;
    };
    let cursor = midY;
    L.forEach(n => {
      const h = n.total * scale;
      band(colL + nodeW, n.y, n.y + n.h, colM, cursor, cursor + h, n.synthetic ? 'sk-link-save' : 'sk-link-in', `${n.label}: ${tl(n.total)}`);
      cursor += h;
    });
    cursor = midY;
    R.forEach(n => {
      const h = n.total * scale;
      band(colM + nodeW, cursor, cursor + h, colR, n.y, n.y + n.h, n.key === '__kept' ? 'sk-link-save' : 'sk-link-out', `${n.label}: ${tl(n.total)}`);
      cursor += h;
    });
    svg('rect', {x: colM, y: midY, width: nodeW, height: midH, rx: 3, class: 'sk-mid'}, root);
    const node = (n, x, cls, side) => {
      const g = svg('g', {class: 'sk-node', tabindex: 0, role: 'button', 'aria-label': `${n.label}: ${tl(n.total)}`}, root);
      svg('rect', {x, y: n.y, width: nodeW, height: n.h, rx: 3, class: cls}, g);
      const tx = side === 'L' ? x - 8 : x + nodeW + 8, anchor = side === 'L' ? 'end' : 'start';
      const ty = n.y + n.h / 2;
      const t = svg('text', {x: tx, y: ty - 1, 'text-anchor': anchor, class: 'sk-label'}, g);
      t.textContent = n.label.length > 26 ? n.label.slice(0, 25) + '…' : n.label;
      svg('text', {x: tx, y: ty + 13, 'text-anchor': anchor, class: 'sk-sub'}, g).textContent = `${tl(n.total)} · %${Math.round(n.total / total * 100)}`;
      const open = () => {
        if (n.key === '__rest') openList(`Diğer ${n.items.length} gider kalemi`, r.start.slice(0, 7), n.items);
        else if (!n.synthetic) openCategory(n.key);
      };
      g.addEventListener('click', open);
      g.addEventListener('keydown', e => {if (e.key === 'Enter') open();});
    };
    L.forEach(n => node(n, colL, n.synthetic ? 'sk-save-n' : 'sk-in', 'L'));
    R.forEach(n => node(n, colR, n.key === '__kept' ? 'sk-save-n' : 'sk-out-n', 'R'));
    svg('text', {x: colM + nodeW / 2, y: height - 1, 'text-anchor': 'middle', class: 'sk-sub'}, root).textContent = `Toplam ${tl(total)}`;
    // the same numbers as clickable tables
    const rowsHtml = (items, sum) => items.length ? items.map(c => `<tr data-open="${c.key || '__none'}"><td>${icon(c.key)}${esc(c.label)}</td><td class="num">${tl(c.total)}</td><td class="num chg">%${Math.round(c.total / Math.max(1, sum) * 100)}</td><td class="go">›</td></tr>`).join('') :
      '<tr><td class="fx-empty">Kayıt yok</td></tr>';
    $('inTable').querySelector('tbody').innerHTML = rowsHtml(r.in_by_category, inTotal) + `<tr class="sum"><td><b>Toplam gelen</b></td><td class="num"><b>${tl(inTotal)}</b></td><td></td><td></td></tr>`;
    $('outTable').querySelector('tbody').innerHTML = rowsHtml(r.by_category, outTotal) + `<tr class="sum"><td><b>Toplam giden</b></td><td class="num"><b>${tl(outTotal)}</b></td><td></td><td></td></tr>`;
    document.querySelectorAll('#inTable [data-open], #outTable [data-open]').forEach(tr => tr.addEventListener('click', () => openCategory(tr.dataset.open)));
  }

  // a list of categories (the "Diğer" slice, the long tail of the flow) → each opens its detail
  function openList(title, month, items) {
    $('otherTitle').textContent = title;
    $('otherSub').textContent = monthLabel(month, 'long') + ' · bir kaleme dokunun, hareketleri açılır';
    const sum = items.reduce((s, i) => s + i.total, 0);
    $('otherTable').querySelector('tbody').innerHTML = items.sort((a, b) => b.total - a.total).map(i =>
      `<tr data-open="${i.key || '__none'}" data-month="${month}"><td>${icon(i.key)}${esc(i.label)}</td><td class="num">${tl(i.total)}</td><td class="num chg">%${Math.round(i.total / Math.max(1, sum) * 100)}</td><td class="go">›</td></tr>`).join('') +
      `<tr class="sum"><td><b>Toplam</b></td><td class="num"><b>${tl(sum)}</b></td><td></td><td></td></tr>`;
    $('otherTable').querySelectorAll('[data-open]').forEach(tr => tr.addEventListener('click', () => {$('otherDialog').close(); openCategory(tr.dataset.open, tr.dataset.month);}));
    $('otherDialog').showModal();
  }
  function goSearch(text) {
    $('search').value = text; state.rows = 60; state.category = ''; $('categoryFilter').value = '';
    renderMovements(state.data.report);
    $('movementRows').closest('.fx-card').scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // ---------------------------------------------------------------- icons
  const ICONS = {yemek: '🍽️', market: '🛒', akaryakit: '⛽', ulasim: '🚕', kargo: '📦', reklam: '📣', sosyal_medya: '📱',
    hizmet: '🧾', personel: '👥', yazilim: '💻', ofis: '🗂️', faturalar: '💡', alisveris: '🛍️', giyim: '👕', saglik: '🩺',
    eglence: '🎉', aile: '👪', borc: '🤝', kart_borcu: '💳', kira: '🏠', banka: '🏦', nakit: '💵', diger: '•', hatirlanmiyor: '❔',
    gelir: '💼', aile_gelen: '👪', tahsilat: '💳', iade: '↩️', borc_donus: '🤝', diger_gelen: '•', gelir_destegi: '🫶', ic_transfer: '⇄', aracilik: '⇢', haric: '⊘', '': '❓', __none: '❓'};
  const icon = (key, big) => `<span class="fx-ic${big ? ' big' : ''}" aria-hidden="true">${ICONS[key] ?? '•'}</span>`;

  // ------------------------------------------------------------ review
  function renderReview(r) {
    $('review').innerHTML = r.review.length ? r.review.map((s, i) => i === 0 ? `<p>${esc(s)}</p>` : '').join('') +
      `<p>${r.review.slice(1).map(esc).join(' ')}</p>` : '<p class="fx-empty">Bu dönem için yorumlanacak hareket yok.</p>';
  }

  // ------------------------------------------------------------ budgets
  function renderBudgets(items) {
    const box = $('budgets');
    if (!items.length) {
      box.innerHTML = '<p class="fx-empty">Henüz bütçe yok. “Bütçe ekle” ile örneğin yemeğe aylık 5.000 ₺ limit koyun; %80 ve %100’de telefonunuza bildirim gelir.</p>';
      return;
    }
    const stateText = {ok: 'Yolunda', warn: 'Dikkat', over: 'Aşıldı'};
    box.innerHTML = items.map(b => {
      const fill = Math.min(100, b.pct), mark = Math.min(100, b.expected_pct);
      return `<div class="fx-budget"><div class="top">${icon(b.category)}<strong>${esc(b.label)}</strong><span class="num">${tl(b.spent)} <span class="chg">/ ${tl(b.limit)}</span></span></div>
        <svg viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label="${esc(b.label)}: yüzde ${b.pct}"><rect class="trk" width="100" height="10" rx="5"/>
        ${b.spent ? `<rect class="bud-${b.state}" width="${Math.max(2, fill)}" height="10" rx="5"/>` : ''}<line class="bud-mark" x1="${mark}" x2="${mark}" y1="0" y2="10" vector-effect="non-scaling-stroke"/></svg>
        <div class="meta"><span><span class="st ${b.state}">${stateText[b.state]}</span> · %${b.pct}${b.left >= 0 ? ` · kalan ${tl(b.left)}` : ` · ${tl(-b.left)} fazla`}</span><span><button type="button" data-budget-edit="${b.category}" data-budget-limit="${b.limit / 100}">Değiştir</button> · <button type="button" data-budget-del="${b.category}">Kaldır</button></span></div></div>`;
    }).join('');
    box.querySelectorAll('[data-budget-edit]').forEach(btn => btn.addEventListener('click', () => {
      $('budgetForm').hidden = false; $('budgetCategory').value = btn.dataset.budgetEdit;
      $('budgetForm').elements.monthly.value = btn.dataset.budgetLimit; $('budgetForm').elements.monthly.focus();
    }));
    box.querySelectorAll('[data-budget-del]').forEach(btn => btn.addEventListener('click', async () => {
      try {await api('/api/money/budget', {category: btn.dataset.budgetDel, monthly: ''}); await load();} catch (x) {error(x.message);}
    }));
  }

  // ---------------------------------------------------- scope over 6 months
  function renderScopeTrend(r) {
    const host = $('scopeTrend');
    const max = niceMax(Math.max(1, ...r.trend.map(m => m.out)));
    const {root, width, height} = frame(host, 170);
    const left = 44, right = width - 4, top = 8, plotH = height - 34;
    const ax = svg('g', {class: 'ax'}, root);
    yAxis(ax, left, right, top, plotH, max, 3);
    const group = (right - left) / r.trend.length, bw = Math.min(26, group - 14);
    r.trend.forEach((m, i) => {
      const bx = left + i * group + (group - bw) / 2;
      let base = top + plotH;
      const parts = SCOPES.filter(k => m.scopes[k] > 0);
      parts.forEach((k, j) => {
        const h = m.scopes[k] / max * plotH, y0 = base - h;
        if (j === parts.length - 1) svg('path', {d: barPath(bx, y0, bw, Math.max(h, 1)), class: 's-' + k}, root);
        else svg('rect', {x: bx, y: y0 + 1, width: bw, height: Math.max(h - 2, .5), class: 's-' + k}, root);
        base = y0;
      });
      svg('text', {x: bx + bw / 2, y: height - 9, 'text-anchor': 'middle'}, ax).textContent = monthLabel(m.month);
      const hit = svg('rect', {x: left + i * group, y: top, width: group, height: plotH, class: 'hit', tabindex: 0}, root);
      hover(hit, () => `<b>${monthLabel(m.month, 'long')} · ${tl(m.out)}</b>` + SCOPES.filter(k => m.scopes[k]).map(k =>
        `<span class="k">${esc(k === 'none' ? 'Belirsiz' : state.data.scopes[k])}: ${tl(m.scopes[k])}</span>`).join(''));
    });
  }

  // ------------------------------------------------------ category dialog
  // owner: "tıkladığımda neler olduğunu görebilmek… düzeltebiliyorsam düzeltebilmek istiyorum"
  const dialogState = {key: '', month: '', sub: null, party: null, data: null};
  async function openCategory(key, month = '') {
    try {
      const d = await api('/api/money/category?' + new URLSearchParams({key, day: $('day').value, scope: state.scope, account: state.account, month, book: state.book}));
      Object.assign(dialogState, {key, month, sub: null, party: null, data: d});
      $('catIcon').textContent = ICONS[key] ?? '•';
      $('catTitle').textContent = d.label;
      $('catSub').textContent = `${monthLabel(d.month, 'long')} · ${state.scope ? (state.scope === 'none' ? 'belirsiz' : state.data.scopes[state.scope]) : 'tüm hesaplar'}${state.account ? ' · ' + state.account : ''}${d.direction === 'in' ? ' · gelen para' : ''}`;
      $('catStats').innerHTML = `<div><p class="lbl">${d.direction === 'in' ? 'Bu ay gelen' : 'Bu ay'}</p><p class="v">${tl(d.total)}</p></div><div><p class="lbl">İşlem</p><p class="v">${d.count}</p></div>
        <div><p class="lbl">Ortalama işlem</p><p class="v">${tl(d.average_ticket)}</p></div><div><p class="lbl">Önceki aylar ort.</p><p class="v">${tl(d.monthly_average)}</p></div>`;
      $('catPartyTitle').textContent = d.direction === 'in' ? 'Kimden geldi' : 'En çok ödenen';
      if (!$('catDialog').open) $('catDialog').showModal();
      drawCategoryTrend(d);
      drawCategoryLists();
    } catch (x) {error(x.message);}
  }
  function drawCategoryTrend(d) {
    const host = $('catTrend');
    const max = niceMax(Math.max(1, ...d.trend.map(t => t.total)));
    const {root, width, height} = frame(host, 170);
    const left = 44, right = width - 4, top = 14, plotH = height - 38;
    const ax = svg('g', {class: 'ax'}, root);
    yAxis(ax, left, right, top, plotH, max, 3);
    const group = (right - left) / d.trend.length, bw = Math.min(34, group - 16);
    d.trend.forEach((t, i) => {
      const bx = left + i * group + (group - bw) / 2, h = t.total / max * plotH;
      if (t.total) {
        const bar = svg('path', {d: barPath(bx, top + plotH - h, bw, h), class: 'bar-mark mix-seg'}, root);
        svg('text', {x: bx + bw / 2, y: top + plotH - h - 5, 'text-anchor': 'middle', class: 'val-label'}, root).textContent = short(t.total);
        hover(bar, () => `<b>${monthLabel(t.month, 'long')}</b>${tl(t.total)} · ${t.count} işlem<br>Dokunun: o ayı açın`);
        bar.addEventListener('click', () => openCategory(dialogState.key, t.month));
      }
      svg('text', {x: bx + bw / 2, y: height - 9, 'text-anchor': 'middle'}, ax).textContent = monthLabel(t.month);
    });
  }
  function drawCategoryLists() {
    const d = dialogState.data;
    const bars = (items, attr, on) => {
      const max = Math.max(1, ...items.map(i => i.total));
      return items.length ? items.map(i => `<div class="fx-bar-row click${on === i.key ? ' on' : ''}" ${attr}="${esc(i.key)}" tabindex="0"><span class="name" title="${esc(i.label)}">${esc(i.label)} <span class="chg">· ${i.count}</span></span><span class="amt">${tl(i.total)}</span>
        <svg viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true"><rect class="trk" width="100" height="6" rx="3"/><rect class="fil" width="${Math.max(1.5, i.total / max * 100)}" height="6" rx="3"/></svg></div>`).join('') : '<p class="fx-empty">Kayıt yok.</p>';
    };
    $('catSubs').innerHTML = bars(d.subcategories, 'data-sub', dialogState.sub) +
      (d.subcategories.length === 1 && !d.subcategories[0].key ? '<p class="fx-note">Alt kalem henüz seçilmemiş; aşağıdaki listeden her ödemeye alt kalem yazabilirsiniz (ör. Kira, Muhasebe).</p>' : '');
    $('catParties').innerHTML = bars(d.parties.map(p => ({...p, key: p.label})), 'data-pty', dialogState.party);
    $('catSubs').querySelectorAll('[data-sub]').forEach(el => el.addEventListener('click', () => {dialogState.sub = dialogState.sub === el.dataset.sub ? null : el.dataset.sub; drawCategoryLists();}));
    $('catParties').querySelectorAll('[data-pty]').forEach(el => el.addEventListener('click', () => {dialogState.party = dialogState.party === el.dataset.pty ? null : el.dataset.pty; drawCategoryLists();}));
    const rows = d.movements.filter(m => (dialogState.sub === null || (m.subcategory || '') === dialogState.sub) && (dialogState.party === null || m.party === dialogState.party));
    $('catMoveNote').textContent = `· ${rows.length} hareket${dialogState.sub !== null ? ` · alt kalem: ${dialogState.sub || 'seçilmedi'}` : ''}${dialogState.party ? ` · ${dialogState.party}` : ''}`;
    const cats = state.data.categories;
    const subOptions = (d.suggestions || []).map(v => `<option value="${esc(v)}">`).join('');
    $('catMoves').innerHTML = rows.length ? rows.map(m => {
      const map = catMap(m.direction);
      return `<tr data-id="${m.id}"><td>${esc(dayLabel(m.tx_date))}</td><td class="party"><div title="${esc(m.party)}">${esc(m.party)}</div><small>${esc(m.account)}${m.note ? ' · ' + esc(m.note) : ''}</small></td>
        <td><select data-f="category" aria-label="Ne için">${opts(map, m.category, 'Belirlenmedi')}</select></td>
        <td><input class="sub" data-f="subcategory" list="dlgSub-${m.id}" value="${esc(m.subcategory || '')}" placeholder="Alt kalem" maxlength="40" aria-label="Alt kalem"><datalist id="dlgSub-${m.id}">${subOptions}</datalist></td>
        <td><select data-f="scope" aria-label="Kimin hesabına">${opts(state.data.scopes, m.scope, 'Belirlenmedi')}</select></td>
        <td class="num">${m.direction === 'in' ? '+' : '−'}${tl2(m.amount_cents)}</td>
        <td class="save-cell"><label><input type="checkbox" data-f="remember"> Hep böyle</label><button type="button" class="fx-btn small" data-save>Kaydet</button>${NOT_COUNTED.includes(m.category) ? '' : '<button type="button" class="fx-btn small ghost" data-drop title="Hareket kalır ama hiçbir toplama girmez">Çıkar</button>'}</td></tr>`;
    }).join('') : '<tr><td colspan="7" class="fx-empty">Bu süzgeçte hareket yok.</td></tr>';
    $('catMoves').querySelectorAll('[data-drop]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {await api('/api/money/classify', {id: btn.closest('tr').dataset.id, category: 'haric', scope: btn.closest('tr').querySelector('[data-f="scope"]').value, remember: false});
        await load(); await openCategory(dialogState.key, dialogState.month);}
      catch (x) {error(x.message); btn.disabled = false;}
    }));
    $('catMoves').querySelectorAll('[data-save]').forEach(btn => btn.addEventListener('click', async () => {
      const tr = btn.closest('tr'), f = n => tr.querySelector(`[data-f="${n}"]`);
      btn.disabled = true;
      try {
        await api('/api/money/classify', {id: tr.dataset.id, category: f('category').value, subcategory: f('subcategory').value.trim(),
          scope: f('scope').value, remember: f('remember').checked});
        btn.textContent = 'Kaydedildi ✓'; btn.classList.add('saved');
        await load();
        await openCategory(dialogState.key, dialogState.month);
      } catch (x) {error(x.message); btn.disabled = false;}
    }));
  }

  // ------------------------------------------------------------------ KPI
  function sparkline(host, values, h = 34, labels) {
    if (!host) return;
    host.textContent = '';
    if (values.filter(Boolean).length < 2) return;
    const {root, width, height} = frame(host, h);
    const max = Math.max(...values) || 1, step = (width - 6) / (values.length - 1);
    const pts = values.map((v, i) => [3 + i * step, height - 3 - (v / max) * (height - 8)]);
    svg('path', {d: `M${pts[0][0]},${height} ` + pts.map(p => `L${p[0]},${p[1]}`).join(' ') + ` L${pts.at(-1)[0]},${height}Z`, class: 'area'}, root);
    svg('path', {d: 'M' + pts.map(p => p.join(',')).join(' L'), class: 'line'}, root);
    svg('circle', {cx: pts.at(-1)[0], cy: pts.at(-1)[1], r: 3, class: 'end'}, root);
    if (labels) {
      svg('text', {x: 3, y: height - 2}, root).textContent = labels[0];
      svg('text', {x: width - 3, y: height - 2, 'text-anchor': 'end'}, root).textContent = labels[1];
    }
  }
  function renderKpis(r) {
    const prevName = {month: 'geçen ay', week: 'geçen hafta', day: 'önceki gün'}[state.view];
    const partial = state.view === 'month' && r.elapsed_days < r.length_days;
    const compareOut = partial ? r.same_point_prev : r.prev_out_total;
    $('kOut').textContent = tl(r.out_total);
    $('dOut').innerHTML = `${change(r.out_total, compareOut)} ${partial ? `geçen ayın ilk ${r.elapsed_days} gününe göre` : prevName + 'a göre'}`;
    $('kIn').textContent = tl(r.in_total);
    $('dIn').innerHTML = `${change(r.in_total, r.prev_in_total, true)} ${prevName}a göre`;
    const net = r.in_total - r.out_total;
    $('kNet').textContent = (net < 0 ? '−' : '+') + tl(Math.abs(net));
    $('dNet').textContent = r.in_total ? `Birikim oranı %${Math.round(net / r.in_total * 100)}` : 'Bu dönemde gelen yok';
    if (r.forecast) {
      $('kFourLabel').textContent = 'Ay sonu tahmini';
      $('kFour').textContent = tl(r.forecast);
      $('dFour').textContent = `Günlük ${tl(r.out_total / Math.max(1, r.elapsed_days))} tempoyla`;
    } else {
      $('kFourLabel').textContent = 'Günlük ortalama';
      $('kFour').textContent = tl(r.out_total / Math.max(1, r.elapsed_days || r.length_days));
      $('dFour').textContent = `${r.active_days} günde harcama`;
    }
    sparkline($('sOut'), r.trend.map(m => m.out), 70, [monthLabel(r.trend[0].month), monthLabel(r.trend.at(-1).month)]);
    $('heroSay').textContent = r.review.slice(1, 3).join(' ');
  }

  // ------------------------------------------------------------ pace chart
  function renderPace(r) {
    const host = $('paceChart');
    if (state.view === 'day') {
      $('paceCard').querySelector('h2').textContent = 'Günün hareketleri';
      $('paceLegend').hidden = true;
      const rows = r.movements.filter(m => m.direction === 'out' && !NOT_COUNTED.includes(m.category));
      host.innerHTML = rows.length ? `<ul class="fx-list">${rows.map(m => `<li><span class="t">${esc(m.party)}</span><span class="num">${tl2(m.amount_cents)}</span><small>${esc(state.data.categories[m.category] || 'Belirlenmedi')} · ${esc(m.account)}</small></li>`).join('')}</ul>` : '<p class="fx-empty">Bu gün harcama yok.</p>';
      $('paceNote').textContent = longDay(r.start);
      return;
    }
    $('paceCard').querySelector('h2').textContent = 'Harcama temposu';
    $('paceLegend').hidden = false;
    const cur = r.pace.current, prev = r.pace.previous, n = r.length_days;
    const fc = r.forecast;
    const max = niceMax(Math.max(cur.at(-1) || 0, prev.at(-1) || 0, fc || 0));
    const {root, width, height} = frame(host, innerWidth < 1000 ? 250 : Math.max(260, Math.min(400, $('insights').getBoundingClientRect().height - 40)));
    const left = 52, right = width - 64, top = 12, plotH = height - 40;
    const x = i => left + (right - left) * (n === 1 ? 0 : i / (n - 1));
    const xp = i => left + (right - left) * (prev.length === 1 ? 0 : i / (prev.length - 1));
    const y = v => top + plotH - v / max * plotH;
    const ax = svg('g', {class: 'ax'}, root);
    yAxis(ax, left, right, top, plotH, max);
    const labels = state.view === 'week' ? [...Array(n).keys()] : [0, 6, 13, 20, n - 1];
    for (const i of labels) {
      const d = new Date(parse(r.start)); d.setDate(d.getDate() + i);
      svg('text', {x: x(i), y: height - 8, 'text-anchor': 'middle'}, ax).textContent = state.view === 'week' ? d.toLocaleDateString('tr-TR', {weekday: 'short'}) : d.getDate();
    }
    if (prev.length) svg('path', {d: 'M' + prev.map((v, i) => `${xp(i)},${y(v)}`).join(' L'), class: 'pace-prev'}, root);
    if (cur.length) {
      svg('path', {d: `M${x(0)},${y(0)} ` + cur.map((v, i) => `L${x(i)},${y(v)}`).join(' ') + ` L${x(cur.length - 1)},${y(0)}Z`, class: 'pace-area'}, root);
      svg('path', {d: 'M' + cur.map((v, i) => `${x(i)},${y(v)}`).join(' L'), class: 'pace-cur'}, root);
      if (fc && cur.length < n) svg('path', {d: `M${x(cur.length - 1)},${y(cur.at(-1))} L${x(n - 1)},${y(fc)}`, class: 'pace-fc'}, root);
      svg('text', {x: x(cur.length - 1) + 8, y: y(cur.at(-1)) + 4, class: 'end-label'}, root).textContent = short(cur.at(-1)) + ' ₺';
    }
    if (prev.length) svg('text', {x: right + 8, y: y(prev.at(-1)) + 4, class: 'val-label'}, root).textContent = short(prev.at(-1)) + ' ₺';
    // crosshair: one hit column per day
    const cross = svg('line', {y1: top, y2: top + plotH, class: 'cross', visibility: 'hidden'}, root);
    const mc = svg('circle', {r: 4, class: 'marker cur', visibility: 'hidden'}, root);
    const mp = svg('circle', {r: 4, class: 'marker prev', visibility: 'hidden'}, root);
    const colW = (right - left) / Math.max(1, n - 1);
    for (let i = 0; i < n; i++) {
      const hit = svg('rect', {x: x(i) - colW / 2, y: top, width: colW, height: plotH, class: 'hit', tabindex: i % 7 === 0 ? 0 : -1}, root);
      const d = new Date(parse(r.start)); d.setDate(d.getDate() + i);
      const show = () => {
        const pv = prev[Math.min(i, prev.length - 1)];
        cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
        if (i < cur.length) {mc.setAttribute('cx', x(i)); mc.setAttribute('cy', y(cur[i])); mc.setAttribute('visibility', 'visible');} else mc.setAttribute('visibility', 'hidden');
        if (pv !== undefined) {mp.setAttribute('cx', xp(Math.min(i, prev.length - 1))); mp.setAttribute('cy', y(pv)); mp.setAttribute('visibility', 'visible');}
        const b = hit.getBoundingClientRect();
        tip.show(`<b>${state.view === 'week' ? d.toLocaleDateString('tr-TR', {weekday: 'long', day: 'numeric', month: 'long'}) : `Ayın ${i + 1}. günü`}</b>` +
          (i < cur.length ? `<span class="k"><i class="cur"></i>Bu dönem: ${tl(cur[i])}</span>` : '') +
          (pv !== undefined ? `<span class="k"><i class="prev"></i>Önceki dönem: ${tl(pv)}</span>` : ''), b.left + b.width / 2, b.top + 40);
      };
      const hide = () => {tip.hide(); [cross, mc, mp].forEach(e => e.setAttribute('visibility', 'hidden'));};
      hit.addEventListener('mouseenter', show); hit.addEventListener('mouseleave', hide);
      hit.addEventListener('focus', show); hit.addEventListener('blur', hide);
    }
    const partial = r.elapsed_days < n;
    $('paceNote').textContent = partial ?
      `Ayın ${r.elapsed_days}. günü: ${tl(r.out_total)} · geçen ay bu noktada ${tl(r.same_point_prev)}` :
      `Toplam ${tl(r.out_total)} · önceki dönem ${tl(r.prev_out_total)}`;
  }

  // ------------------------------------------------------------ insights
  function renderInsights(r) {
    const icon = {warn: '!', good: '✓', info: 'i'};
    $('insights').innerHTML = r.insights.length ? r.insights.map(i =>
      `<li class="${i.tone}"><span class="ic ${i.tone}" aria-hidden="true">${icon[i.tone] || 'i'}</span><div><strong>${esc(i.title)}</strong><span>${esc(i.text)}</span></div></li>`).join('') :
      '<li class="info"><span class="ic info">i</span><div><strong>Henüz yorumlanacak kadar veri yok</strong><span>Döküm veya ekstre yükledikçe burada karşılaştırmalar görünür.</span></div></li>';
  }

  // ------------------------------------------------------- cash flow 6 ay
  function renderFlow(r) {
    const host = $('flowChart');
    const months = r.trend;
    const max = niceMax(Math.max(1, ...months.map(m => Math.max(m.in, m.out))));
    const {root, width, height} = frame(host, 230);
    const left = 48, right = width - 6, top = 10, plotH = height - 38;
    const ax = svg('g', {class: 'ax'}, root);
    yAxis(ax, left, right, top, plotH, max);
    const group = (right - left) / months.length, bw = Math.min(22, (group - 14) / 2);
    months.forEach((m, i) => {
      const gx = left + i * group + group / 2;
      [['in', m.in, gx - bw - 1], ['out', m.out, gx + 1]].forEach(([k, v, bx]) => {
        if (v > 0) {
          const h = v / max * plotH;
          svg('path', {d: barPath(bx, top + plotH - h, bw, h), class: 'cf-' + k}, root);
        }
      });
      svg('text', {x: gx, y: height - 10, 'text-anchor': 'middle'}, ax).textContent = monthLabel(m.month);
      const hit = svg('rect', {x: left + i * group, y: top, width: group, height: plotH, class: 'hit', tabindex: 0}, root);
      hover(hit, () => `<b>${monthLabel(m.month, 'long')}</b><span class="k"><i class="in"></i>Gelen: ${tl(m.in)}</span><span class="k"><i class="out"></i>Harcanan: ${tl(m.out)}</span>Net: ${m.in - m.out < 0 ? '−' : '+'}${tl(Math.abs(m.in - m.out))}<br>Dokunun: bu ayı açın`);
      hit.style.cursor = 'pointer';
      hit.addEventListener('click', () => {$('day').value = m.month + '-01'; setView('month'); scrollTo({top: 0, behavior: 'smooth'});});
    });
  }
  function renderFlowTable(r) {
    $('flowTable').querySelector('tbody').innerHTML = [...r.trend].reverse().map(m => {
      const net = m.in - m.out;
      return `<tr><td>${esc(monthLabel(m.month, 'long'))}</td><td class="num">${tl(m.in)}</td><td class="num">${tl(m.out)}</td><td class="num ${net < 0 ? 'chg up' : 'chg down'}">${net < 0 ? '−' : '+'}${tl(Math.abs(net))}</td></tr>`;
    }).join('');
  }
  function renderMix(r) {
    const host = $('mixChart');
    const cats = r.trend_categories;
    const keys = [...cats.map(c => c.key), '__other'];
    const known = cats.map(c => c.key).filter(k => k);
    const colour = k => k === '__other' ? 'c-other' : k === '' ? 'c-none' : MIX[known.indexOf(k)];
    const max = niceMax(Math.max(1, ...r.trend.map(m => m.out)));
    const {root, width, height} = frame(host, 230);
    const left = 48, right = width - 6, top = 10, plotH = height - 38;
    const ax = svg('g', {class: 'ax'}, root);
    yAxis(ax, left, right, top, plotH, max);
    const group = (right - left) / r.trend.length, bw = Math.min(34, group - 18);
    r.trend.forEach((m, i) => {
      const bx = left + i * group + (group - bw) / 2;
      let base = top + plotH;
      const parts = m.mix.filter(p => p.total > 0);
      parts.forEach((p, j) => {
        const h = p.total / max * plotH;
        const cls = colour(p.key);
        const top2 = base - h;
        const seg = j === parts.length - 1 ? svg('path', {d: barPath(bx, top2, bw, Math.max(h, 1)), class: cls + ' mix-seg'}, root)
          : svg('rect', {x: bx, y: top2 + 1, width: bw, height: Math.max(h - 2, 0.5), class: cls + ' mix-seg'}, root);  // 2px surface gap
        const label = p.key === '__other' ? 'Diğer kalemler' : (state.data.categories[p.key] || 'Belirlenmedi');
        hover(seg, () => `<b>${esc(label)}</b>${monthLabel(m.month, 'long')}: ${tl(p.total)}<br>Dokunun: kalemleri açın`);
        seg.addEventListener('click', () => {
          if (p.key === '__other') {
            const top5 = new Set(keys);
            openList(`${monthLabel(m.month, 'long')} · diğer kalemler`, m.month, Object.entries(m.all || {}).filter(([k]) => !top5.has(k))
              .map(([k, v]) => ({key: k, label: state.data.categories[k] || 'Belirlenmedi', total: v})));
          } else openCategory(p.key || '__none', m.month);
        });
        base = top2;
      });
      svg('text', {x: bx + bw / 2, y: height - 10, 'text-anchor': 'middle'}, ax).textContent = monthLabel(m.month);
      const hit = svg('rect', {x: left + i * group, y: top, width: group, height: plotH, class: 'hit', tabindex: 0, 'pointer-events': 'none'}, root);
      hover(hit, () => `<b>${monthLabel(m.month, 'long')} · ${tl(m.out)}</b>` + m.mix.filter(p => p.total).map(p =>
        `<span class="k">${esc(p.key === '__other' ? 'Diğer' : state.data.categories[p.key] || 'Belirlenmedi')}: ${tl(p.total)}</span>`).join(''));
    });
    $('mixLegend').innerHTML = keys.map((k, i) => {
      const total = r.trend.reduce((s, m) => s + (m.mix.find(p => p.key === k)?.total || 0), 0);
      const label = k === '__other' ? 'Diğer' : (cats[i].label || 'Belirlenmedi');
      return `<li class="click" data-legend="${k}"><i class="sq ${colour(k)}"></i>${esc(label)}<span class="amt">${tl(total)}</span></li>`;
    }).join('');
    $('mixLegend').querySelectorAll('[data-legend]').forEach(li => li.addEventListener('click', () => {
      const k = li.dataset.legend;
      if (k === '__other') {
        const top5 = new Set(keys), all = {};
        r.trend.forEach(m => Object.entries(m.all || {}).forEach(([c, v]) => {if (!top5.has(c)) all[c] = (all[c] || 0) + v;}));
        openList('Son 6 ay · diğer kalemler', r.trend.at(-1).month, Object.entries(all).map(([c, v]) => ({key: c, label: state.data.categories[c] || 'Belirlenmedi', total: v})));
      } else openCategory(k || '__none');
    }));
  }

  // ------------------------------------------------------- category table
  function renderCategories(r) {
    const total = r.out_total || 1, max = Math.max(1, ...r.by_category.map(c => c.total));
    const body = $('categoryTable').querySelector('tbody');
    body.innerHTML = r.by_category.length ? r.by_category.map(c => {
      const key = c.key || '__none';
      const diff = c.total - c.previous;
      const dtext = c.previous ? `<span class="chg ${diff > 0 ? 'up' : diff < 0 ? 'down' : ''}">${diff > 0 ? '+' : diff < 0 ? '−' : ''}${tl(Math.abs(diff))}</span>` : '<span class="chg">yeni</span>';
      return `<tr class="click${state.category === key ? ' active' : ''}" data-cat="${key}" tabindex="0"><td><span class="cat-cell">${icon(c.key)}${esc(c.label)}</span></td><td class="num">${tl(c.total)}</td>
        <td class="share"><div class="share-bar"><svg viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true"><rect class="trk" width="100" height="8" rx="4"/><rect class="fil" width="${Math.max(1.5, c.total / max * 100)}" height="8" rx="4"/></svg><small>%${Math.round(c.total / total * 100)}</small></div></td>
        <td class="num">${c.previous ? tl(c.previous) : '–'}</td><td class="num">${dtext}</td><td class="num">${c.count}</td></tr>`;
    }).join('') : '<tr><td colspan="6" class="fx-empty">Bu dönemde harcama yok.</td></tr>';
    body.querySelectorAll('tr[data-cat]').forEach(tr => {
      const pick = () => openCategory(tr.dataset.cat);
      tr.addEventListener('click', pick); tr.addEventListener('keydown', e => {if (e.key === 'Enter') pick();});
    });
  }

  // ------------------------------------------------------------ calendar
  function renderCalendar(r) {
    const host = $('calendar');
    if (state.view !== 'month') {
      $('calendarCard').hidden = true; return;
    }
    $('calendarCard').hidden = false;
    const totals = Object.fromEntries(r.series.map(s => [s.date, s.total]));
    const values = Object.values(totals).sort((a, b) => a - b);
    const q = p => values[Math.min(values.length - 1, Math.floor(p * values.length))] || 0;
    const steps = [q(.2), q(.4), q(.6), q(.8)];
    const level = v => !v ? '' : v <= steps[0] ? 'h1' : v <= steps[1] ? 'h2' : v <= steps[2] ? 'h3' : v <= steps[3] ? 'h4' : 'h5';
    const start = parse(r.start), pad = (start.getDay() + 6) % 7;
    let html = WEEKDAYS.map(d => `<span class="wd">${d}</span>`).join('') + '<span class="pad"></span>'.repeat(pad);
    const t = today();
    for (let i = 0; i < r.length_days; i++) {
      const d = new Date(start); d.setDate(d.getDate() + i);
      const k = iso(d), v = totals[k] || 0;
      html += `<button type="button" class="${level(v)}${k === t ? ' today' : ''}" data-day="${k}" aria-label="${esc(longDay(k))}: ${esc(tl(v))}">${d.getDate()}${v ? `<small>${short(v)}</small>` : ''}</button>`;
    }
    host.innerHTML = html;
    host.querySelectorAll('button[data-day]').forEach(b => {
      const k = b.dataset.day, v = totals[k] || 0;
      hover(b, () => `<b>${esc(longDay(k))}</b>${v ? `Harcama: ${tl(v)}<br>Dokunun: günü açın` : 'Harcama yok'}`);
      b.addEventListener('click', () => {$('day').value = k; setView('day');});
    });
    const busiest = r.series.reduce((a, s) => s.total > (a?.total || 0) ? s : a, null);
    $('calendarNote').textContent = busiest ? `En yoğun gün ${dayLabel(busiest.date)} · ${tl(busiest.total)}` : 'Bu ay harcama yok';
  }
  function renderWeekday(r) {
    const host = $('weekdayChart');
    const max = niceMax(Math.max(1, ...r.weekday));
    const {root, width, height} = frame(host, 200);
    const left = 44, right = width - 6, top = 16, plotH = height - 40;
    const ax = svg('g', {class: 'ax'}, root);
    yAxis(ax, left, right, top, plotH, max, 3);
    const slot = (right - left) / 7, bw = Math.min(30, slot - 12);
    const peak = r.weekday.indexOf(Math.max(...r.weekday));
    r.weekday.forEach((v, i) => {
      const bx = left + i * slot + (slot - bw) / 2;
      if (v) svg('path', {d: barPath(bx, top + plotH - v / max * plotH, bw, v / max * plotH), class: 'bar-mark'}, root);
      if (i === peak && v) svg('text', {x: bx + bw / 2, y: top + plotH - v / max * plotH - 5, 'text-anchor': 'middle', class: 'val-label'}, root).textContent = short(v);
      svg('text', {x: bx + bw / 2, y: height - 10, 'text-anchor': 'middle'}, ax).textContent = WEEKDAYS[i];
      const hit = svg('rect', {x: left + i * slot, y: top, width: slot, height: plotH, class: 'hit', tabindex: 0}, root);
      hover(hit, () => `<b>${['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'][i]}</b>Son 90 günde ${tl(v)}`);
    });
  }

  // ------------------------------------------------- scope, parties, recurring
  function renderScope(r) {
    const host = $('scopeChart');
    const by = Object.fromEntries(r.by_scope.map(s => [s.key || 'none', s]));
    const items = SCOPES.filter(k => by[k]).map(k => ({...by[k], key: k}));
    if (!items.length) {host.innerHTML = '<p class="fx-empty">Bu dönemde harcama yok.</p>'; return;}
    const total = items.reduce((s, i) => s + i.total, 0);
    host.innerHTML = '';
    const bar = svg('svg', {viewBox: '0 0 1000 14', preserveAspectRatio: 'none', class: 'stack-svg', role: 'img', 'aria-label': 'Hesap başlığına göre dağılım'}, host);
    let x = 0;
    items.forEach((it, i) => {
      const w = it.total / total * 1000, last = i === items.length - 1;
      svg('rect', {x, y: 0, width: Math.max(1, w - (last ? 0 : 3)), height: 14, rx: 3, class: 's-' + it.key}, bar);
      x += w;
    });
    const ul = document.createElement('ul'); ul.className = 'fx-legend';
    ul.innerHTML = items.map(it => `<li class="click" data-scope-pick="${it.key}"><i class="sq s-${it.key}"></i>${esc(it.key === 'none' ? 'Belirsiz' : state.data.scopes[it.key])}<span class="amt">${tl(it.total)} · %${Math.round(it.total / total * 100)}</span></li>`).join('');
    host.appendChild(ul);
    ul.querySelectorAll('[data-scope-pick]').forEach(li => li.addEventListener('click', () => {setScope(li.dataset.scopePick); load().catch(x => error(x.message)); scrollTo({top: 0, behavior: 'smooth'});}));
  }
  function renderParties(r) {
    const host = $('partyList');
    const items = r.top_parties.slice(0, 8), max = Math.max(1, ...items.map(i => i.total));
    host.innerHTML = items.length ? items.map(i => `<div class="fx-bar-row click" data-party="${esc(i.label)}" tabindex="0"><span class="name" title="${esc(i.label)}">${esc(i.label)}</span><span class="amt">${tl(i.total)}</span>
      <svg viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true"><rect class="trk" width="100" height="6" rx="3"/><rect class="fil" width="${Math.max(1.5, i.total / max * 100)}" height="6" rx="3"/></svg></div>`).join('') :
      '<p class="fx-empty">Bu dönemde harcama yok.</p>';
    host.querySelectorAll('[data-party]').forEach(row => row.addEventListener('click', () => goSearch(row.dataset.party)));
  }
  function renderRecurring(r) {
    const host = $('recurring');
    host.innerHTML = r.recurring.length ? `<ul class="fx-list">${r.recurring.slice(0, 7).map(i =>
      `<li class="click" data-party="${esc(i.party)}"><span class="t">${esc(i.party)}</span><span class="num">${tl(i.monthly_estimate)}/ay</span><small>${i.declared ? 'anlaşma' + (i.last_date ? ' · son ' + esc(dayLabel(i.last_date)) : '') : `${i.months} ayda · tipik ${tl(i.typical)} · son ${esc(dayLabel(i.last_date))}`}${i.category ? ' · ' + esc(state.data.categories[i.category] || '') : ''}</small></li>`).join('')}</ul>` +
      `<p class="fx-note">Aylık toplam ≈ ${tl(r.recurring.reduce((s, i) => s + i.monthly_estimate, 0))}</p>` :
      '<p class="fx-empty">Henüz iki farklı ayda tekrar eden ödeme yok. Daha fazla ay yüklendikçe görünür.</p>';
    host.querySelectorAll('[data-party]').forEach(li => li.addEventListener('click', () => goSearch(li.dataset.party)));
  }

  // ------------------------------------------------- questions & agreements
  const opts = (map, sel, empty) => (empty !== undefined ? `<option value="">${esc(empty)}</option>` : '') +
    Object.entries(map).map(([k, v]) => `<option value="${k}"${k === sel ? ' selected' : ''}>${esc(v)}</option>`).join('');
  // one row per movement with its date (owner: "toplu gösterilmesin, ayrı ayrı bölebilirim")
  function renderQuestions(items) {
    const total = items.reduce((sum, q) => sum + Number(q.amount_cents), 0);
    $('questionCount').textContent = items.length ? `${items.length} hareket · ${tl(total)}` : 'Tamam';
    const box = $('questions');
    if (!items.length) {box.innerHTML = '<p class="fx-empty">Açıklaması eksik hareket kalmadı.</p>'; return;}
    state.qShown = state.qShown || 8;
    const ic = uncounted();
    const shown = items.slice(0, state.qShown);
    box.innerHTML = shown.map(q => {
      const incoming = q.direction === 'in';
      const cats = incoming ? {...state.data.in_categories, ...ic} : {...state.data.out_categories, ...ic};
      const detail = (q.description || '').replace(/^\d{2}\.\d{2}\.\d{4}\s*/, '').slice(0, 90);
      return `<form class="fx-q${incoming ? ' in' : ''}" data-id="${q.id}">
      <div class="who"><span>${incoming ? '<span class="dir in">Gelen</span>' : '<span class="dir">Giden</span>'}${esc(q.party)}</span><span class="num">${incoming ? '+' : '−'}${tl2(q.amount_cents)}</span></div>
      <p class="fx-note"><b>${esc(longDay(q.tx_date))}</b> · ${esc(q.account)}${q.party_count > 1 ? ` · bu kişiyle ${q.party_count} hareket var` : ''}${detail ? `<br>${esc(detail)}` : ''}</p>
      <div class="row"><select name="category" required aria-label="${incoming ? 'Ne için geldi' : 'Ne için'}">${opts(cats, '', incoming ? 'Ne için geldi?' : 'Ne için?')}</select>
      <select name="scope" aria-label="Kimin hesabına">${opts(state.data.scopes, '', 'Kimin hesabına?')}</select>
      <input class="sub" name="subcategory" list="subList" placeholder="Alt kalem" maxlength="40" aria-label="Alt kalem"></div>
      <div class="row"><input class="note" name="note" maxlength="300" placeholder="Not (ör. krem satışı, kira payı)" aria-label="Not">
      <label title="İşaretlenirse bu kişinin etiketlenmemiş bütün ${incoming ? 'gelen' : 'giden'} paraları da aynı olur"><input type="checkbox" name="remember"> Hepsi böyle</label><button type="submit" class="fx-btn">Kaydet</button></div></form>`;
    }).join('') + (items.length > shown.length ? `<div class="fx-more"><button type="button" class="fx-btn ghost" id="moreQuestions">${items.length - shown.length} hareket daha göster</button></div>` : '');
    box.querySelectorAll('form').forEach(f => f.addEventListener('submit', async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f));
      const btn = f.querySelector('button[type=submit]'); btn.disabled = true;
      try {
        await api('/api/money/classify', {id: f.dataset.id, category: d.category, scope: d.scope, subcategory: (d.subcategory || '').trim(),
          note: (d.note || '').trim(), remember: Boolean(d.remember)});
        await load();
      } catch (x) {error(x.message); btn.disabled = false;}
    }));
    const more = $('moreQuestions');
    if (more) more.addEventListener('click', () => {state.qShown += 8; renderQuestions(items);});
  }
  // owner, 02.11.2026: money that came in and left within two days, explained by where it went
  function renderFlows(r) {
    const items = r.flows || [];
    $('flowCount').textContent = items.length ? `${items.length} eşleşme${r.passthrough_total ? ' · ' + tl(r.passthrough_total) + ' aracılık' : ''}` : '';
    const box = $('flows');
    if (!items.length) {box.innerHTML = '<p class="fx-empty">Bu dönemde gelip aynı günlerde başka yere giden para yok.</p>'; return;}
    box.innerHTML = items.map(f => {
      const pass = f.kind === 'aracilik', sent = f.outs.reduce((s, o) => s + o.amount, 0);
      return `<div class="fx-link${pass ? ' pass' : ''}" data-in="${f.in_id}">
        <div class="who"><span><span class="dir in">Gelen</span>${esc(f.party)}</span><span class="num">+${tl2(f.amount)}</span></div>
        <p class="fx-note"><b>${esc(longDay(f.date))}</b> · ${esc(f.account)}${f.transfer ? ` · ${esc(f.transfer.other)}'tan${f.transfer.origin ? ` (oraya ${esc(f.transfer.origin)} ödedi)` : ''}` : ''}</p>
        <ul>${f.outs.map(o => `<li><span>→ ${esc(o.party)} <small>${esc(dayLabel(o.date))}${o.category && !NOT_COUNTED.includes(o.category) ? ' · ' + esc(state.data.categories[o.category] || '') : ''}</small></span><span class="num">−${tl2(o.amount)}</span></li>`).join('')}</ul>
        <p class="verdict">${pass ? `<b>Aracılık:</b> ${tl(sent)} başkası adına geçti; ne gelir ne gider sayıldı.${f.amount > sent ? ` Kalan ${tl(f.amount - sent)} sizde kaldı.` : ''}`
          : '<b>Açıklama:</b> bu para bu ödemelere gitti; toplamlar değişmedi.'}${f.status === 'auto' ? ' <span class="tag">Jarvis buldu</span>' : ' <span class="tag">onaylandı</span>'}</p>
        <div class="row">${f.status === 'auto' ? '<button type="button" class="fx-btn small" data-link="ok">Doğru</button>' : ''}
          <button type="button" class="fx-btn small ghost" data-link="${pass ? 'info' : 'pass'}">${pass ? 'Benim harcamamdı' : 'Aracılık say'}</button>
          <button type="button" class="fx-btn small ghost" data-link="reject">Yanlış eşleşme</button></div></div>`;
    }).join('');
    box.querySelectorAll('[data-link]').forEach(b => b.addEventListener('click', async () => {
      b.disabled = true;
      try {await api('/api/money/link', {in_id: b.closest('[data-in]').dataset.in, action: b.dataset.link}); await load();}
      catch (x) {error(x.message); b.disabled = false;}
    }));
  }
  function renderAgreements(items) {
    const box = $('agreements');
    if (!items.length) {box.innerHTML = '<p class="fx-empty">Henüz aylık anlaşma yok.</p>'; return;}
    box.innerHTML = items.map(a => {
      const cur = a.this_month;
      const months = a.months.map(m => `<div class="fx-month${m.current ? ' current' : ''}"><b>${esc(monthLabel(m.month, 'long'))}</b>
        <svg viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true"><rect class="trk" width="100" height="6" rx="3"/>${m.paid ? `<rect class="fil" width="${Math.max(2, m.paid / m.due * 100)}" height="6" rx="3"/>` : ''}</svg>
        ${m.skipped ? 'Çalışma yok' : m.open ? `${tl(m.paid)} / ${tl(m.due)}` : 'Tamamlandı'}</div>`).join('');
      return `<div class="fx-agr"><div class="top"><strong>${esc(a.party)}</strong><span class="meta">${esc(state.data.categories[a.category] || '')}${a.scope ? ' · ' + esc(state.data.scopes[a.scope]) : ''} · aylık ${tl(a.monthly)}${a.ended ? ' · ' + esc(monthLabel(a.ended, 'long')) + ' bitti' : ''}</span></div>
        <p>${a.owed_closed_months ? `<span class="owed">Borç ${tl(a.owed_closed_months)}</span>` : '<span class="settled">Borç yok</span>'}${cur ? ` · bu ay ${tl(cur.paid)} / ${tl(cur.due)}` : ''} · toplam ödenen ${tl(a.paid_total)}</p>
        <div class="fx-months">${months}</div></div>`;
    }).join('');
  }

  // ------------------------------------------------------------ movements
  function renderMovements(r) {
    const q = $('search').value.trim().toLocaleLowerCase('tr-TR'), dir = $('directionFilter').value, cats = state.data.categories;
    let rows = r.movements.filter(m => (!state.category || (m.category || '__none') === state.category) && (!dir || m.direction === dir) &&
      (!q || `${m.party} ${m.note || ''} ${m.account}`.toLocaleLowerCase('tr-TR').includes(q)));
    rows = rows.sort((a, b) => (state.sort === 'amount_cents' ? a.amount_cents - b.amount_cents : a.tx_date.localeCompare(b.tx_date)) * (state.asc ? 1 : -1));
    const shown = rows.slice(0, state.rows);
    const sel = (field, map, value, id) => `<select data-edit="${id}" data-field="${field}" aria-label="${field === 'category' ? 'Ne için' : 'Kimin hesabına'}">${opts(map, value, 'Belirlenmedi')}</select>`;
    $('movementRows').innerHTML = shown.length ? shown.map(m => {
      const map = catMap(m.direction);
      const off = NOT_COUNTED.includes(m.category);
      const passed = m.passed_cents && !off ? `<span class="tag">${tl(m.passed_cents)} aracılık düşüldü</span>` : '';
      const tr = m.transfer;  // the same money in the other book (owner, 02.11.2026)
      const moved = tr ? `<span class="tag move">↔ ${esc(tr.other)}</span>` : '';
      const chain = tr && (tr.origin || tr.onward) ? `<small>${tr.origin ? `${esc(tr.company)}'a gelen: ${esc(tr.origin)}` : `${esc(tr.company)}'dan: ${esc(tr.onward)}`}</small>` : '';
      const act = m.hand ? `<button type="button" class="fx-btn small ghost" data-del="${m.id}" title="Elle eklenen hareketi sil">Sil</button>`
        : m.category === 'ic_transfer' ? ''
        : off ? `<button type="button" class="fx-btn small ghost" data-back="${m.id}" title="Yeniden hesaba kat; ne için olduğunu sonra seçin">Geri al</button>`
        : `<button type="button" class="fx-btn small ghost" data-drop="${m.id}" title="Hareket kalır ama hiçbir toplama girmez">Çıkar</button>`;
      const receipt = m.receipt === 'matched' ? '<span class="tag">fişi var</span>' : m.receipt === 'needed' ? '<span class="tag need">fiş yok</span>' : '';
      return `<tr class="${off ? 'internal' : ''}"><td>${esc(dayLabel(m.tx_date))}</td>
        <td class="party"><div title="${esc(m.party)}">${esc(m.party)}${receipt}${passed}${moved}${m.hand ? '<span class="tag">elle</span>' : ''}</div>${chain}${m.note ? `<small>${esc(m.note)}</small>` : ''}</td>
        <td>${sel('category', map, m.category, m.id)}</td><td><input class="sub" data-edit="${m.id}" data-field="subcategory" list="subList" value="${esc(m.subcategory || '')}" placeholder="—" aria-label="Alt kalem" maxlength="40"></td><td>${sel('scope', state.data.scopes, m.scope, m.id)}</td><td>${esc(m.account)}</td>
        <td class="num ${m.direction === 'in' ? 'amt-in' : 'amt-out'}">${m.direction === 'in' ? '+' : '−'}${tl2(m.amount_cents)}${m.foreign_currency ? `<small>${(m.foreign_cents / 100).toFixed(2)} ${m.foreign_currency}</small>` : ''}${m.passed_cents && !off ? `<small>brüt ${tl2(m.gross_cents)}</small>` : ''}</td><td class="act">${act}</td></tr>`;
    }).join('') : '<tr><td colspan="8" class="fx-empty">Bu süzgeçte hareket yok.</td></tr>';
    $('moreRows').hidden = rows.length <= state.rows;
    $('movementNote').textContent = `${rows.length} hareket${state.category ? ` · ${state.category === '__none' ? 'Belirlenmedi' : cats[state.category]} süzgeci (kategoriye tekrar dokunarak kaldırın)` : ''}`;
    document.querySelectorAll('[data-sort]').forEach(b => {b.classList.toggle('on', b.dataset.sort === state.sort); b.classList.toggle('asc', b.dataset.sort === state.sort && state.asc);});
    const act = async (btn, url, body) => {btn.disabled = true; try {await api(url, body); await load();} catch (x) {error(x.message); btn.disabled = false;}};
    $('movementRows').querySelectorAll('[data-drop]').forEach(b => b.addEventListener('click', () =>
      act(b, '/api/money/classify', {id: b.dataset.drop, category: 'haric', scope: b.closest('tr').querySelector('[data-field=scope]').value, remember: false})));
    $('movementRows').querySelectorAll('[data-back]').forEach(b => b.addEventListener('click', () =>
      act(b, '/api/money/classify', {id: b.dataset.back, category: '', scope: b.closest('tr').querySelector('[data-field=scope]').value, remember: false})));
    $('movementRows').querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => act(b, '/api/money/delete', {id: b.dataset.del})));
    document.querySelectorAll('[data-edit]').forEach(s => s.addEventListener('change', async () => {
      const tr = s.closest('tr');
      try {await api('/api/money/classify', {id: s.dataset.edit, category: tr.querySelector('[data-field=category]').value, subcategory: tr.querySelector('[data-field=subcategory]').value.trim(), scope: tr.querySelector('[data-field=scope]').value, remember: false}); await load();}
      catch (x) {error(x.message);}
    }));
  }

  // ------------------------------------------------------------------ flow
  function render() {
    const r = state.data.report;
    const scopeName = state.scope ? (state.scope === 'none' ? 'hesap başlığı belirsiz' : state.data.scopes[state.scope]) : 'tüm hesaplar';
    const span = state.view === 'day' ? longDay(r.start) : state.view === 'month' ? parse(r.start).toLocaleDateString('tr-TR', {month: 'long', year: 'numeric'}) : `${dayLabel(r.start)} – ${dayLabel(r.end)}`;
    $('rangeLabel').textContent = `${span} · ${scopeName}${state.account ? ' · ' + state.account : ''}`;
    renderKpis(r); renderInsights(r); renderPace(r); renderSankey(r); renderReview(r); renderBudgets(r.budgets || []); renderFlow(r); renderFlowTable(r); renderMix(r); renderCategories(r);
    renderCalendar(r); renderWeekday(r); renderScopeTrend(r); renderScope(r); renderParties(r); renderRecurring(r);
    renderQuestions(state.data.questions); renderFlows(r); renderAgreements(state.data.agreements); renderMovements(r);
  }
  async function load() {
    error('');
    state.data = await api('/api/money/report?' + new URLSearchParams({view: state.view, day: $('day').value, scope: state.scope, account: state.account, book: state.book}));
    renderBooks(state.data.report.books || []);
    const accounts = state.data.report.accounts || [];
    $('accountSelect').innerHTML = '<option value="">Tüm bankalar ve kartlar</option>' + accounts.map(a => `<option value="${esc(a.name)}"${a.name === state.account ? ' selected' : ''}>${esc(a.name)}${a.out ? ' · ' + tl(a.out) : ''}</option>`).join('');
    $('subList').innerHTML = [...new Set(Object.values(state.data.subcategories || {}).flat())].map(v => `<option value="${esc(v)}">`).join('');
    if ($('categoryFilter').options.length === 0) {
      $('categoryFilter').innerHTML = '<option value="">Bütün kategoriler</option><option value="__none">Belirlenmedi</option>' + opts(state.data.categories, '');
      $('ruleCategory').innerHTML = opts(state.data.out_categories, 'sosyal_medya');
      $('ruleScope').innerHTML = opts(state.data.scopes, '', 'Belirlenmedi');
      $('addScope').innerHTML = opts(state.data.scopes, '', 'Belirlenmedi');
      $('addDate').value = today();
      const budgetCats = {...state.data.out_categories}; delete budgetCats.hatirlanmiyor;
      $('budgetCategory').innerHTML = opts(budgetCats, 'yemek');
    }
    $('partyNames').innerHTML = [...new Set(state.data.report.movements.map(m => m.party))].slice(0, 200).map(p => `<option value="${esc(p)}">`).join('');
    $('addCategory').innerHTML = opts(catMap($('addDirection').value), $('addCategory').value, 'Belirlenmedi');
    render();
    loadInvoices().catch(x => {$('invoiceCard').hidden = true; error(x.message);});
    const url = new URL(location.href);
    url.searchParams.set('view', state.view); url.searchParams.set('day', $('day').value);
    if (state.scope) url.searchParams.set('scope', state.scope); else url.searchParams.delete('scope');
    if (state.account) url.searchParams.set('account', state.account); else url.searchParams.delete('account');
    if (state.book !== 'kisisel') url.searchParams.set('book', state.book); else url.searchParams.delete('book');
    history.replaceState(null, '', url);
  }
  function setView(v) {
    state.view = v;
    document.querySelectorAll('[data-view]').forEach(b => {b.classList.toggle('on', b.dataset.view === v); b.setAttribute('aria-pressed', String(b.dataset.view === v));});
    load().catch(x => error(x.message));
  }
  // owner, 02.11.2026: company accounts are separate books, never mixed into his own money
  function renderBooks(books) {
    document.querySelectorAll('[data-book]').forEach(b => {
      const info = books.find(x => x.key === b.dataset.book);
      b.classList.toggle('on', b.dataset.book === state.book); b.setAttribute('aria-selected', String(b.dataset.book === state.book));
      b.title = info ? `${info.count} hareket${info.last ? ' · son ' + dayLabel(info.last) : ''}` : '';
    });
    const cur = books.find(x => x.key === state.book);
    $('bookNote').textContent = state.book === 'kisisel' ? 'Kendi hesaplarınız ve kartlarınız. Şirket hesapları Şirket sekmesinde; karışmaz, iki kez sayılmaz.'
      : cur && cur.count ? `${state.data.books[state.book]} hesabının hareketleri · şahsi tarafa hiç girmez.`
      : `${state.data.books[state.book]} defteri henüz boş. ${state.book === 'lemos' ? 'QNB 146275187' : 'Enpara Şirketim'} dökümleri Gmail bağlanınca kendiliğinden buraya gelir; aşağıdan da yükleyebilirsiniz.`;
  }
  function setBook(b) {
    state.book = b; state.account = ''; state.category = '';
    document.querySelectorAll('[data-book]').forEach(x => {x.classList.toggle('on', x.dataset.book === b); x.setAttribute('aria-selected', String(x.dataset.book === b));});
    const company = b !== 'kisisel';  // Şahsi = his own money; Şirket = Lemos / MOY books
    document.querySelectorAll('[data-side]').forEach(x => {const on = (x.dataset.side === 'sirket') === company; x.classList.toggle('on', on); x.setAttribute('aria-selected', String(on));});
    $('books').hidden = !company;
    $('scopeTabs').hidden = company;  // a company book has one heading: the company itself
    if (company) setScope('');
  }
  // owner, 02.11.2026: MOY's e-invoices (Uyumsoft) line by line, with the movement that paid each
  async function loadInvoices() {
    const card = $('invoiceCard');
    if (state.book === 'kisisel') {card.hidden = true; return;}
    const month = $('day').value.slice(0, 7);
    const d = state.inv = await api('/api/money/invoices?' + new URLSearchParams({book: state.book, month}));
    card.hidden = false;
    $('invNote').textContent = d.connected
      ? `${monthLabel(d.month, 'long')} · ${d.source === 'pdf' ? 'gönderdiğiniz e-fatura PDF\'lerinden' : 'Uyumsoft e-fatura ve e-arşiv · yalnız okunur'}${d.last_fetch ? ' · son çekim ' + new Date(d.last_fetch).toLocaleString('tr-TR', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : ''}`
      : (d.source === 'pdf' ? 'Bu defterin faturaları henüz yok.' : 'Uyumsoft bağlantısı kuruldu; ilk faturalar bir sonraki çekimde gelir.');
    const ins = d.invoices.filter(i => i.box === 'in'), outs = d.invoices.filter(i => i.box === 'out');
    $('invSum').innerHTML = `<div><span>Gelen faturalar</span><b>${tl(d.in_total)}</b><small>${ins.length} fatura</small></div>`
      + `<div><span>Giden faturalar</span><b>${tl(d.out_total)}</b><small>${outs.length} fatura</small></div>`
      + `<div class="${d.unpaid ? 'warn' : ''}"><span>Ödemesi bulunamayan</span><b>${d.unpaid}</b><small>${d.unpaid ? 'gelen fatura · banka hareketi yok' : 'hepsi eşleşti'}</small></div>`
      + `<div class="${d.uncollected ? 'warn' : ''}"><span>Tahsilatı bulunamayan</span><b>${d.uncollected}</b><small>${d.uncollected ? 'giden fatura · PayTR/POS toplu yatar' : 'hepsi eşleşti'}</small></div>`;
    const max = Math.max(1, ...d.by_category.map(c => c.total));
    $('invCats').innerHTML = d.by_category.length ? `<h3 class="fx-h3">Neye harcandı</h3><ul>${d.by_category.map(c =>
      `<li><span>${esc(c.label)}</span><i data-w="${Math.max(2, Math.round(c.total / max * 100))}"></i><b>${tl(c.total)}</b></li>`).join('')}</ul>` : '';
    $('invCats').querySelectorAll('[data-w]').forEach(i => {i.style.width = i.dataset.w + '%';});  // CSP: no inline style
    renderInvoices();
    await loadAnalysis();
  }
  // owner, 02.11.2026: Lemos and L'CARLIÉ are one company but two businesses — split by invoice content
  async function loadAnalysis() {
    const box = $('invAnalysis');
    if (state.book !== 'lemos') {box.hidden = true; return;}
    const a = await api('/api/money/invoice-analysis?' + new URLSearchParams({book: state.book, year: $('day').value.slice(0, 4)}));
    box.hidden = false;
    state.ana = a;
    $('anaNote').textContent = `${a.year} yılı · ${a.parts} fatura kalemi${a.unread ? ` · ${a.unread} faturanın kalemi okunamadı, tedarikçiye göre sınıflandı` : ''}`;
    $('anaBiz').innerHTML = ['lcarlie', 'lemos'].map(k => {const b = a.businesses[k]; return `<div class="biz b-${k}">
        <h4>${esc(b.label)}</h4>
        <dl><dt>Satış</dt><dd>${tl(b.sales)}</dd><dt>Doğrudan gider</dt><dd>−${tl(b.direct_cost)}</dd>
        <dt>Ortak giderden payı <small>%${b.share.toLocaleString('tr-TR')}</small></dt><dd>−${tl(b.shared_cost)}</dd>
        <dt class="r">Kalan</dt><dd class="r ${b.result < 0 ? 'neg' : ''}">${b.result < 0 ? '−' : ''}${tl(Math.abs(b.result))}</dd></dl></div>`;}).join('');
    const flags = [];
    if (a.unclear_sales) flags.push(`Ürünü yazmayan “gıda takviyesi” satışı ${tl(a.unclear_sales)}: hangi işin olduğu belli değil, iki işe de katılmadı.`);
    if (a.group.in || a.group.out) flags.push(`MOY ile grup içi faturalar (${tl(a.group.in + a.group.out)}) ayrı tutuldu.`);
    flags.push(`Bölüştürülen ortak gider: ${tl(a.shared_cost)}.`);
    $('anaFlags').textContent = flags.join(' ');
    $('anaMethod').textContent = a.method;
    drawMonthly(a.monthly);
    drawChannels(a);
    const bars = (id, items, val, label, cls) => {
      const max = Math.max(1, ...items.map(val));
      $(id).innerHTML = items.length ? items.map(x => `<li><span>${label(x)}</span><i class="${cls ? cls(x) : ''}" data-w="${Math.max(2, Math.round(val(x) / max * 100))}"></i><b>${tl(val(x))}</b></li>`).join('')
        : '<li class="empty">Bu dönemde yok.</li>';
      $(id).querySelectorAll('[data-w]').forEach(i => {i.style.width = i.dataset.w + '%';});
    };
    bars('anaProducts', a.products_sold.slice(0, 15), x => x.net, x => `${esc(x.name)} <small>${Math.round(x.qty).toLocaleString('tr-TR')} adet</small>`, () => 'c-lcarlie');
    bars('anaThemes', a.themes.filter(t => t.in > 0).slice(0, 12), x => x.in, x => esc(x.label));
    bars('anaSupp', [...a.supplements.bought.slice(0, 6).map(x => ({...x, side: 'alındı'})), ...a.supplements.sold.slice(0, 6).map(x => ({...x, side: 'satıldı'}))],
      x => x.net, x => `${esc(x.name)} <small>${x.side}</small>`, x => x.side === 'satıldı' ? 'c-out' : 'c-in');
    $('anaSuppNote').textContent = `Alınan ${tl(a.supplements.bought_total)} · satılan ${tl(a.supplements.sold_total)}`;
    bars('anaPromo', a.promo, x => x.net, x => esc(x.name));
    bars('anaBought', a.top_bought, x => x.net, x => esc(x.name));
    // every list carries its total and opens the filter with that list's selection
    const sumOf = (box, pick) => (a.rows || []).filter(r => r.k === state.book && r.b === box && pick(r)).reduce((s, r) => s + r.v, 0);
    const listTotal = (id, total, preset) => {
      const ul = $(id);
      ul.insertAdjacentHTML('beforeend', `<li class="total click" tabindex="0"><span>Toplam · süz</span><i hidden></i><b>${tl(total)}</b></li>`);
      ul.querySelector('li.total').addEventListener('click', () => openExplore(preset));
    };
    listTotal('anaProducts', sumOf('out', r => r.z === 'lcarlie'), {box: 'out', book: state.book, biz: 'lcarlie', group: 'item'});
    listTotal('anaThemes', sumOf('in', () => true), {box: 'in', book: state.book, group: 'theme'});
    listTotal('anaPromo', sumOf('in', r => r.t === 'promosyon_matbaa'), {box: 'in', book: state.book, theme: 'promosyon_matbaa', group: 'party'});
    listTotal('anaBought', sumOf('in', () => true), {box: 'in', book: state.book, group: 'item'});
    $('anaThemes').querySelectorAll('li:not(.total):not(.empty)').forEach((li, i) => {
      const t = a.themes.filter(x => x.in > 0)[i]; if (!t) return;
      li.classList.add('click'); li.addEventListener('click', () => openExplore({box: 'in', book: state.book, theme: t.key, group: 'party'}));
    });
    $('anaProducts').querySelectorAll('li:not(.total):not(.empty)').forEach((li, i) => {
      const p = a.products_sold[i]; if (!p) return;
      li.classList.add('click'); li.addEventListener('click', () => openExplore({box: 'out', book: state.book, text: p.name, group: 'month'}));
    });
    initExplore(a);
  }

  // ------------------------------------------------- filter and total (owner, 02.11.2026)
  // "L'CARLIÉ toplam satışını göreyim, VIREON hariç de görebileyim; promosyon matbaada yalnız Yeni Nesil ya da Mim"
  const fold = s => String(s || '').toLocaleLowerCase('tr-TR').replace(/ı/g, 'i').normalize('NFD').replace(/[̀-ͯ]/g, '');
  const ex = {box: 'out', limit: 15};
  function initExplore(a) {
    const rows = a.rows || [], o = (v, label) => `<option value="${esc(v)}">${esc(label)}</option>`;
    $('exBiz').innerHTML = o('', 'Bütün işler') + Object.entries(a.business_labels).filter(([k]) => rows.some(r => r.z === k)).map(([k, v]) => o(k, v)).join('');
    $('exTheme').innerHTML = o('', 'Bütün konular') + Object.entries(a.themes_all).filter(([k]) => rows.some(r => r.t === k)).map(([k, v]) => o(k, v)).join('');
    $('exChan').innerHTML = o('', 'Bütün kanallar') + Object.entries(a.channel_labels).map(([k, v]) => o(k, v)).join('');
    $('exMonth').innerHTML = o('', `${a.year} tamamı`) + [...new Set(rows.map(r => r.m))].sort().map(m => o(m, monthLabel(m, 'long'))).join('');
    if (!ex.ready) {
      ex.ready = true;
      ['exBook', 'exBiz', 'exTheme', 'exChan', 'exMonth', 'exMode', 'exGroup'].forEach(id => $(id).addEventListener('change', () => {ex.limit = 15; renderExplore();}));
      $('exText').addEventListener('input', () => {ex.limit = 15; renderExplore();});
      document.querySelectorAll('[data-exbox]').forEach(b => b.addEventListener('click', () => {ex.box = b.dataset.exbox; ex.limit = 15; renderExplore();}));
      $('exReset').addEventListener('click', () => openExplore({box: ex.box, book: ''}, false));
      $('exMore').addEventListener('click', () => {ex.limit = 1e9; renderExplore();});
    }
    renderExplore();
  }
  function openExplore(p, scroll = true) {
    ex.box = p.box || 'out'; ex.limit = 15;
    $('exBook').value = p.book || ''; $('exBiz').value = p.biz || ''; $('exTheme').value = p.theme || '';
    $('exChan').value = p.chan || ''; $('exMonth').value = p.month || ''; $('exText').value = p.text || '';
    $('exMode').value = p.mode || 'only'; $('exGroup').value = p.group || 'item';
    renderExplore();
    if (scroll) $('anaExplore').scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  function renderExplore() {
    const a = state.ana; if (!a) return;
    document.querySelectorAll('[data-exbox]').forEach(b => {const on = b.dataset.exbox === ex.box; b.classList.toggle('on', on); b.setAttribute('aria-selected', String(on));});
    $('exChan').hidden = ex.box !== 'out';
    const book = $('exBook').value, biz = $('exBiz').value, theme = $('exTheme').value, chan = ex.box === 'out' ? $('exChan').value : '', month = $('exMonth').value;
    const base = a.rows.filter(r => r.b === ex.box && (!book || r.k === book) && (biz ? r.z === biz : r.z !== 'grup') && (!theme || r.t === theme) && (!chan || r.c === chan) && (!month || r.m === month));
    const terms = $('exText').value.split(',').map(t => fold(t).trim()).filter(Boolean), except = $('exMode').value === 'except';
    const hit = r => terms.some(t => fold(`${r.p} ${r.n} ${r.f}`).includes(t));
    const shown = terms.length ? base.filter(r => except ? !hit(r) : hit(r)) : base;
    const sum = list => list.reduce((s, r) => s + r.v, 0), total = sum(base), part = sum(shown);
    const word = ex.box === 'out' ? 'satış' : 'alış';
    $('exTiles').innerHTML = `<div class="t"><span>Toplam ${word}</span><b>${tl(total)}</b><small>${base.length} kalem · KDV hariç${biz ? '' : ' · grup içi hariç'}</small></div>`
      + (terms.length ? `<div class="t total"><span>${except ? 'Hariç tutulunca' : 'Yalnız bunlar'}</span><b>${tl(part)}</b><small>${shown.length} kalem · %${total ? Math.round(part / total * 100) : 0}</small></div>`
        + `<div class="t"><span>${except ? 'Çıkarılan' : 'Geri kalan'}</span><b>${tl(total - part)}</b><small>${base.length - shown.length} kalem</small></div>` : '');
    const by = $('exGroup').value, labels = {...a.themes_all}, groups = new Map();
    const keyOf = r => by === 'party' ? (r.f || (r.c ? a.channel_labels[r.c] : '') || '—') : by === 'theme' ? labels[r.t] || r.t : by === 'month' ? r.m
      : by === 'biz' ? a.business_labels[r.z] || r.z : by === 'chan' ? a.channel_labels[r.c] || '—' : (r.p || r.n || r.f || '—');
    shown.forEach(r => {const k = keyOf(r), g = groups.get(k) || {net: 0, qty: 0, n: 0}; g.net += r.v; g.qty += r.q; g.n += 1; groups.set(k, g);});
    let items = [...groups.entries()].map(([name, g]) => ({name, ...g}));
    items = by === 'month' ? items.sort((x, y) => x.name.localeCompare(y.name)) : items.sort((x, y) => y.net - x.net);
    const max = Math.max(1, ...items.map(i => Math.abs(i.net)));
    $('exList').innerHTML = items.length ? items.slice(0, ex.limit).map(i => `<li><span>${esc(by === 'month' ? monthLabel(i.name, 'long') : i.name)} <small>${by === 'item' && i.qty ? Math.round(i.qty).toLocaleString('tr-TR') + ' adet · ' : ''}${i.n} kalem</small></span><i class="${ex.box === 'out' ? 'c-lcarlie' : ''}" data-w="${Math.max(2, Math.round(Math.abs(i.net) / max * 100))}"></i><b>${i.net < 0 ? '−' : ''}${tl(Math.abs(i.net))}</b></li>`).join('')
      : '<li class="empty">Bu seçimde kalem yok.</li>';
    $('exList').querySelectorAll('[data-w]').forEach(i => {i.style.width = i.dataset.w + '%';});
    $('exMoreWrap').hidden = items.length <= ex.limit;
  }
  // owner, 02.11.2026: invoices + Wix + Trendyol, one total; an order with an invoice is counted once
  const CHANNELS = [['dogrudan', 'Doğrudan'], ['wix', 'Wix'], ['trendyol', 'Trendyol']];
  function drawChannels(a) {
    const byKey = Object.fromEntries((a.channels || []).map(c => [c.key, c]));
    $('chanNote').textContent = `${a.year} · KDV hariç · faturası olan sipariş faturadan sayılır, olmayan siparişten eklenir`;
    $('chanTiles').innerHTML = CHANNELS.map(([k, label]) => {const c = byKey[k] || {net: 0, from_invoice: 0, orders_only: 0};
      const pct = a.total_sales ? Math.round(c.net / a.total_sales * 100) : 0;
      return `<div class="t ch-${k}"><span><i class="sq ch-${k}"></i>${label}</span><b>${tl(c.net)}</b><small>%${pct}${k !== 'dogrudan' && c.orders_only ? ` · ${tl(c.orders_only)} faturasız sipariş` : ''}</small></div>`;}).join('')
      + `<div class="t total"><span>Toplam satış</span><b>${tl(a.total_sales)}</b><small>L’CARLIÉ ${tl(a.businesses.lcarlie.sales)} · Lemos ${tl(a.businesses.lemos.sales)}</small></div>`;
    const host = $('chanMonthly'); host.innerHTML = '';
    const rows = a.channel_monthly || [];
    if (!rows.length) return;
    const W = Math.max(320, host.clientWidth || 640), H = 200, pad = {l: 8, r: 8, t: 10, b: 24};
    const max = Math.max(1, ...rows.map(r => CHANNELS.reduce((s, [k]) => s + Math.max(0, r[k] || 0), 0)));
    const g = svg('svg', {viewBox: `0 0 ${W} ${H}`, class: 'fx-svg', role: 'img', 'aria-label': 'Aylık satış kanallara göre'}, host);
    const step = (W - pad.l - pad.r) / rows.length, bw = Math.max(6, Math.min(34, step - 10));
    svg('line', {x1: pad.l, x2: W - pad.r, y1: H - pad.b, y2: H - pad.b, class: 'axis'}, g);
    rows.forEach((r, i) => {
      const x = pad.l + i * step + (step - bw) / 2; let y = H - pad.b;
      CHANNELS.forEach(([k, label]) => {
        const v = Math.max(0, r[k] || 0); if (!v) return;
        const h = v / max * (H - pad.t - pad.b);
        y -= h;
        const rect = svg('rect', {x, y: y + 1, width: bw, height: Math.max(0, h - 2), rx: 2, class: 'ch-' + k}, g);  // 2px surface gap
        svg('title', {}, rect).textContent = `${monthLabel(r.month, 'long')} · ${label}: ${tl(v)}`;
      });
      const t = svg('text', {x: x + bw / 2, y: H - 6, 'text-anchor': 'middle', class: 'tick'}, g);
      t.textContent = monthLabel(r.month);
    });
  }
  function drawMonthly(rows) {
    const host = $('anaMonthly'); host.innerHTML = '';
    if (!rows.length) {host.innerHTML = '<p class="fx-note">Bu dönemde satış yok.</p>'; return;}
    const W = Math.max(320, host.clientWidth || 640), H = 200, pad = {l: 8, r: 8, t: 10, b: 24};
    const max = Math.max(1, ...rows.map(r => Math.max(r.out_lcarlie || 0, r.out_lemos || 0)));
    const g = svg('svg', {viewBox: `0 0 ${W} ${H}`, class: 'fx-svg', role: 'img', 'aria-label': 'Aylık satış: L’CARLIÉ ve Lemos'}, host);
    const step = (W - pad.l - pad.r) / rows.length, bw = Math.max(4, Math.min(22, step / 2 - 4));
    svg('line', {x1: pad.l, x2: W - pad.r, y1: H - pad.b, y2: H - pad.b, class: 'axis'}, g);
    rows.forEach((r, i) => {
      const x0 = pad.l + i * step + step / 2;
      [['out_lcarlie', 's-lcarlie', -bw - 1], ['out_lemos', 's-lemos', 1]].forEach(([k, cls, dx]) => {
        const v = r[k] || 0, h = v / max * (H - pad.t - pad.b);
        const rect = svg('rect', {x: x0 + dx, y: H - pad.b - h, width: bw, height: Math.max(0, h), rx: 3, class: cls}, g);
        svg('title', {}, rect).textContent = `${monthLabel(r.month, 'long')} · ${k === 'out_lcarlie' ? 'L’CARLIÉ' : 'Lemos'}: ${tl(v)}`;
      });
      const t = svg('text', {x: x0, y: H - 6, 'text-anchor': 'middle', class: 'tick'}, g);
      t.textContent = monthLabel(r.month);
    });
  }
  const UNITS = {C62: 'adet', NIU: 'adet', MON: 'ay', ANN: 'yıl', DAY: 'gün', HUR: 'saat', KWH: 'kWh', LTR: 'lt', KGM: 'kg', MTR: 'm', MTK: 'm²', PA: 'paket', SET: 'set'};
  function renderInvoices() {
    const d = state.inv, box = state.invBox || 'in';
    document.querySelectorAll('[data-invbox]').forEach(b => {const on = b.dataset.invbox === box; b.classList.toggle('on', on); b.setAttribute('aria-selected', String(on));});
    const list = d.invoices.filter(i => i.box === box);
    if (!list.length) {$('invList').innerHTML = `<p class="fx-note">Bu ay ${box === 'in' ? 'gelen' : 'giden'} fatura yok.</p>`; return;}
    $('invList').innerHTML = list.map(i => {
      const dead = ['Canceled', 'Declined', 'Draft'].includes(i.status);
      const pay = i.movement_id
        ? `<span class="tag good">${box === 'out' ? 'Tahsil edildi' : 'Ödendi'} · ${esc(i.pay_label)} · ${dayLabel(i.pay_date)}</span>`
        : `<span class="tag need">${box === 'out' ? 'Tahsilat bulunamadı' : 'Ödeme bulunamadı'}</span>`;
      const lines = i.lines.map(l => `<tr><td>${esc(l.name)}</td><td class="num">${Number(l.quantity).toLocaleString('tr-TR')} ${esc(UNITS[l.unit] || l.unit)}</td><td class="num">${tl2(l.net_cents)}</td><td class="num">${l.vat_percent == null ? '' : '%' + Number(l.vat_percent).toLocaleString('tr-TR')}</td></tr>`).join('');
      return `<details class="fx-invoice${dead ? ' dead' : ''}"><summary>
          <span class="d">${dayLabel(i.issue_date)}</span>
          <span class="p">${esc(i.party)}${dead ? ' <span class="tag">' + (i.status === 'Draft' ? 'taslak' : 'iptal/ret') + '</span>' : ''}</span>
          <span class="c">${box === 'in' ? esc(d.categories[i.category] || i.category) : (i.scenario === 'eArchive' ? 'e-arşiv' : 'e-fatura')}</span>
          <b class="a">${tl2(i.payable_cents)}</b>${pay}</summary>
        <div class="fx-invoice-body">
          <p class="fx-note">No ${esc(i.number)}${i.party_vkn ? ' · VKN/TCKN ' + esc(i.party_vkn) : ''} · KDV ${tl2(i.tax_cents)}</p>
          <div class="fx-table-wrap"><table class="fx-table compact"><thead><tr><th>Kalem</th><th class="num">Miktar</th><th class="num">Tutar (KDV hariç)</th><th class="num">KDV</th></tr></thead><tbody>${lines || '<tr><td colspan="4">Satır yok</td></tr>'}</tbody></table></div>
          ${box === 'in' ? `<div class="fx-invoice-act"><label>Kategori <select data-invcat="${esc(i.document_id)}">${opts(d.categories, i.category)}</select></label>
            ${i.movement_id ? `<button type="button" class="fx-btn ghost" data-invreject="${esc(i.document_id)}" data-move="${esc(i.movement_id)}">Bu ödeme bu faturanın değil</button>` : ''}</div>` : ''}
        </div></details>`;
    }).join('');
    $('invList').querySelectorAll('[data-invcat]').forEach(s => s.addEventListener('change', async () => {
      try {await api('/api/money/invoice-category', {document_id: s.dataset.invcat, category: s.value}); await loadInvoices();} catch (x) {error(x.message);}
    }));
    $('invList').querySelectorAll('[data-invreject]').forEach(b => b.addEventListener('click', async () => {
      try {await api('/api/money/invoice-payment', {document_id: b.dataset.invreject, movement_id: b.dataset.move, action: 'reject'}); await loadInvoices();} catch (x) {error(x.message);}
    }));
  }
  document.querySelectorAll('[data-invbox]').forEach(b => b.addEventListener('click', () => {state.invBox = b.dataset.invbox; renderInvoices();}));
  function setScope(s) {
    state.scope = s;
    document.querySelectorAll('[data-scope]').forEach(b => {b.classList.toggle('on', b.dataset.scope === s); b.setAttribute('aria-selected', String(b.dataset.scope === s));});
  }
  function shift(n) {
    const d = parse($('day').value);
    if (state.view === 'day') d.setDate(d.getDate() + n); else if (state.view === 'week') d.setDate(d.getDate() + 7 * n); else d.setMonth(d.getMonth() + n, 1);
    $('day').value = iso(d); load().catch(x => error(x.message));
  }
  async function upload(files) {
    if (!files.length) throw new Error('Önce dosya seçin.');
    const b = $('uploadButton'); b.disabled = true;
    let read = 0, added = 0;
    try {
      for (const f of files) {
        if (f.size > 12 * 1024 * 1024) throw new Error(f.name + ': 12 MB sınırını aşıyor.');
        $('uploadResult').textContent = `${f.name} okunuyor… (görsel başına yaklaşık 15 sn)`;
        const res = await fetch('/api/money/upload', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': state.csrf, 'X-File-Name': encodeURIComponent(f.name), 'X-Book': $('uploadBook').value}, body: f});
        const out = await res.json();
        if (!res.ok) throw new Error(f.name + ': ' + (out.error || 'okunamadı'));
        read += out.read; added += out.added;
        if (out.book && out.book !== state.book) $('uploadResult').dataset.book = out.book_label;
      }
      $('uploadResult').textContent = `${read} hareket okundu, ${added} yeni eklendi${read - added ? `, ${read - added} zaten vardı` : ''}.${$('uploadResult').dataset.book ? ` ${$('uploadResult').dataset.book} defterine yazıldı; üstten o deftere geçin.` : ''}`;
      delete $('uploadResult').dataset.book;
      $('files').value = ''; await load();
    } finally {b.disabled = false;}
  }
  async function init() {
    try {
      const s = await api('/api/session');
      if (!s.authenticated) throw new Error('Harcamaları görmek için Jarvis’e giriş yapın.');
      state.csrf = s.csrf_token;
      const p = new URLSearchParams(location.search);  // shareable: ?view=month&day=2026-10-01&scope=kisisel
      $('day').value = /^\d{4}-\d{2}-\d{2}$/.test(p.get('day') || '') ? p.get('day') : today();
      if (['lemos', 'moy', 'lcarlie', 'kisisel', 'aile', 'none'].includes(p.get('scope'))) setScope(p.get('scope'));
      if (['lemos', 'moy'].includes(p.get('book'))) setBook(p.get('book'));
      state.account = p.get('account') || '';
      if (['day', 'week', 'month'].includes(p.get('view'))) {state.view = p.get('view'); document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === state.view));}
      await load();
      if (p.get('cat')) openCategory(p.get('cat'));
    } catch (x) {error(x.message);}
  }
  document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
  document.querySelectorAll('[data-scope]').forEach(b => b.addEventListener('click', () => {setScope(b.dataset.scope); load().catch(x => error(x.message));}));
  document.querySelectorAll('[data-book]').forEach(b => b.addEventListener('click', () => {setBook(b.dataset.book); load().catch(x => error(x.message));}));
  document.querySelectorAll('[data-side]').forEach(b => b.addEventListener('click', () => {
    setBook(b.dataset.side === 'sahsi' ? 'kisisel' : (state.book !== 'kisisel' ? state.book : 'lemos'));
    load().catch(x => error(x.message));
  }));
  document.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () => {
    if (state.sort === b.dataset.sort) state.asc = !state.asc; else {state.sort = b.dataset.sort; state.asc = false;}
    renderMovements(state.data.report);
  }));
  $('accountSelect').addEventListener('change', () => {state.account = $('accountSelect').value; load().catch(x => error(x.message));});
  $('otherClose').addEventListener('click', () => $('otherDialog').close());
  $('otherDialog').addEventListener('click', e => {if (e.target === $('otherDialog')) $('otherDialog').close();});
  $('kOut').closest('.fx-hero-main').addEventListener('click', () => $('categoryTable').scrollIntoView({behavior: 'smooth', block: 'start'}));
  $('kIn').parentElement.addEventListener('click', () => $('flowCard').scrollIntoView({behavior: 'smooth', block: 'start'}));
  $('prev').addEventListener('click', () => shift(-1));
  $('next').addEventListener('click', () => shift(1));
  $('day').addEventListener('change', () => load().catch(x => error(x.message)));
  $('search').addEventListener('input', () => {state.rows = 60; renderMovements(state.data.report);});
  $('directionFilter').addEventListener('change', () => renderMovements(state.data.report));
  $('categoryFilter').addEventListener('change', () => {state.category = $('categoryFilter').value; renderCategories(state.data.report); renderMovements(state.data.report);});
  $('moreRows').addEventListener('click', () => {state.rows += 100; renderMovements(state.data.report);});
  $('toggleRule').addEventListener('click', () => {$('ruleForm').hidden = !$('ruleForm').hidden;});
  $('toggleAdd').addEventListener('click', () => {$('addForm').hidden = !$('addForm').hidden;});
  $('addDirection').addEventListener('change', () => {$('addCategory').innerHTML = opts(catMap($('addDirection').value), '', 'Belirlenmedi');});
  $('addForm').addEventListener('submit', async e => {
    e.preventDefault();
    try {await api('/api/money/add', {...Object.fromEntries(new FormData($('addForm'))), book: state.book}); $('addForm').reset(); $('addDate').value = today(); $('addForm').hidden = true; await load();}
    catch (x) {error(x.message);}
  });
  $('toggleBudget').addEventListener('click', () => {$('budgetForm').hidden = !$('budgetForm').hidden;});
  $('budgetForm').addEventListener('submit', async e => {
    e.preventDefault();
    try {await api('/api/money/budget', Object.fromEntries(new FormData($('budgetForm')))); $('budgetForm').reset(); $('budgetForm').hidden = true; await load();}
    catch (x) {error(x.message);}
  });
  $('catClose').addEventListener('click', () => $('catDialog').close());
  $('catDialog').addEventListener('click', e => {if (e.target === $('catDialog')) $('catDialog').close();});
  $('ruleForm').addEventListener('submit', async e => {
    e.preventDefault();
    try {await api('/api/money/rule', Object.fromEntries(new FormData($('ruleForm')))); $('ruleForm').reset(); $('ruleForm').hidden = true; await load();}
    catch (x) {error(x.message);}
  });
  $('uploadForm').addEventListener('submit', async e => {e.preventDefault(); try {await upload([...$('files').files]);} catch (x) {error(x.message); $('uploadResult').textContent = '';}});
  let resizeTimer;
  addEventListener('resize', () => {clearTimeout(resizeTimer); resizeTimer = setTimeout(() => state.data && render(), 150);});
  init();
})();
