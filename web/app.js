/* AI 缓存清理 · 前端 */
(() => {
  'use strict';

  const TOKEN = document.querySelector('meta[name=token]').content;
  const AGE_STEPS = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365];
  const AGE_LABEL = ['全部', '1 天前', '3 天前', '7 天前', '14 天前', '30 天前', '60 天前', '90 天前', '半年前', '一年前'];
  const AGE_SHORT = ['全部', '1天', '3天', '7天', '14天', '30天', '60天', '90天', '半年', '1年'];
  const CAT_COLORS = {
    cache: '#4e79a7', log: '#59a14f', session: '#e15759', checkpoint: '#f28e2b', temp: '#76b7b2',
    version: '#d4a72c', runtime: '#b07aa1', model: '#9c755f', package: '#ff9da7', crash: '#a5978b',
    data: '#8cc0de', other: '#a0a0a8',
  };

  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem('aiclean.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('aiclean.' + k, JSON.stringify(v)); } catch { /* 隐私模式等情况下忽略 */ } },
  };

  function fmt(n) {
    if (!n) return '0 B';
    const u = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n : n >= 100 ? n.toFixed(0) : n.toFixed(1)) + ' ' + u[i];
  }
  function ago(ts) {
    if (!ts) return '';
    const d = (Date.now() / 1000 - ts) / 86400;
    if (d < 1) return '今天';
    if (d < 30) return Math.floor(d) + ' 天前';
    if (d < 365) return Math.floor(d / 30) + ' 个月前';
    return (d / 365).toFixed(1) + ' 年前';
  }

  async function api(path, body) {
    const r = await fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  const ICON = {
    check: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    chev: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
    down: '<svg class="chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
    back: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>',
    warn: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
    info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
    trash: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>',
    ok: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    sun: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    moon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
  };

  // ------------------------------------------------------------ 状态
  const S = {
    data: null, items: [], byId: {}, tools: {},
    selected: new Set(), ages: {},
    colorBy: store.get('colorBy', 'priority'), sizeBy: store.get('sizeBy', 'total'),
    mode: 'recycle', zoom: null, focus: null, closed: new Set(['4', '5']), busy: false,
  };

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const prioColor = (p) => css('--p' + p);
  const prioLabel = (p) => S.data?.priorities?.[p]?.label || '';
  const ageOf = (it) => (it.age_by ? (S.ages[it.id] ?? it.default_age) : 0);
  const cleanable = (it) => (it.selectable ? it.buckets[Math.max(0, AGE_STEPS.indexOf(ageOf(it)))] || 0 : 0);
  const toolName = (k) => S.tools[k]?.name || k;
  const catName = (k) => S.data?.categories?.[k] || k;

  function shade(hex, pct) {
    const n = parseInt(hex.slice(1), 16);
    const f = (c) => Math.round(pct < 0 ? c * (1 + pct) : c + (255 - c) * pct);
    return '#' + [n >> 16, (n >> 8) & 255, n & 255].map((c) => f(c).toString(16).padStart(2, '0')).join('');
  }

  function colorOf(it, idx = 0) {
    if (S.colorBy === 'tool') {
      const c = S.tools[it.tool]?.color || '#999999';
      return S.zoom ? shade(c, [0, -0.18, 0.16, -0.32, 0.3][idx % 5]) : c; // 放大单个工具时用深浅区分各块
    }
    if (S.colorBy === 'category') return CAT_COLORS[it.category] || '#999';
    return prioColor(it.priority);
  }
  function textOn(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) return '#fff';
    const n = parseInt(m[1], 16), r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    const L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    return L > 0.36 ? 'rgba(0,0,0,.82)' : '#fff';
  }

  // ------------------------------------------------------------ 方块图布局（squarified）
  function squarify(nodes, x, y, w, h) {
    const out = [];
    const items = nodes.filter((n) => n.value > 0).sort((a, b) => b.value - a.value);
    const total = items.reduce((s, n) => s + n.value, 0);
    if (!total || w <= 0 || h <= 0) return out;
    const scale = (w * h) / total;
    let rest = items.map((n) => ({ node: n, area: n.value * scale }));
    const worst = (row, side) => {
      const s = row.reduce((a, r) => a + r.area, 0);
      let max = -Infinity, min = Infinity;
      for (const r of row) { max = Math.max(max, r.area); min = Math.min(min, r.area); }
      return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
    };
    while (rest.length) {
      const side = Math.min(w, h);
      const row = [rest[0]];
      let i = 1;
      while (i < rest.length && worst([...row, rest[i]], side) <= worst(row, side)) { row.push(rest[i]); i++; }
      rest = rest.slice(i);
      const s = row.reduce((a, r) => a + r.area, 0);
      if (w >= h) {
        const rw = s / h; let cy = y;
        for (const r of row) { const rh = r.area / rw; out.push({ node: r.node, x, y: cy, w: rw, h: rh }); cy += rh; }
        x += rw; w -= rw;
      } else {
        const rh = s / w; let cx = x;
        for (const r of row) { const rw2 = r.area / rh; out.push({ node: r.node, x: cx, y, w: rw2, h: rh }); cx += rw2; }
        y += rh; h -= rh;
      }
    }
    return out;
  }

  const valueOf = (it) => (S.sizeBy === 'clean' ? cleanable(it) : it.total);

  function renderTreemap() {
    const box = $('#treemap');
    box.innerHTML = '';
    if (!S.data) return;
    const W = box.clientWidth, H = box.clientHeight;
    const groups = {};
    for (const it of S.items) {
      if (S.zoom && it.tool !== S.zoom) continue;
      const v = valueOf(it);
      if (v <= 0) continue;
      (groups[it.tool] ||= { key: it.tool, value: 0, items: [] });
      groups[it.tool].value += v;
      groups[it.tool].items.push({ value: v, item: it });
    }
    const gl = Object.values(groups);
    if (!gl.length) {
      box.append(el('div', 'map-empty', S.sizeBy === 'clean' ? '当前没有可清理的内容' : '没有发现 AI 工具的数据'));
      return;
    }
    const GAP = 2;
    for (const g of squarify(gl, 0, 0, W, H)) {
      const grp = g.node;
      const gx = g.x + GAP, gy = g.y + GAP, gw = g.w - GAP * 2, gh = g.h - GAP * 2;
      if (gw < 2 || gh < 2) continue;
      const showHead = !S.zoom && gw > 70 && gh > 46;
      const head = showHead ? 24 : 0;
      const pad = S.zoom ? 0 : 3;
      if (!S.zoom) {
        const ge = el('div', 'tm-group');
        Object.assign(ge.style, { left: gx + 'px', top: gy + 'px', width: gw + 'px', height: gh + 'px' });
        if (showHead) {
          const t = S.tools[grp.key] || {};
          const run = t.running?.length ? `<span class="run"><span class="dot" style="background:var(--warning)"></span>运行中</span>` : '';
          const hd = el('div', 'tm-ghead', `<span class="dot" style="background:${t.color}"></span>${esc(t.name || grp.key)}<span class="gsize tabular">${fmt(grp.value)}</span>${run}`);
          hd.title = `查看 ${t.name || grp.key} 的详细分布`;
          hd.onclick = () => { S.zoom = grp.key; renderAll(); };
          ge.append(hd);
        }
        box.append(ge);
      }
      squarify(grp.items, gx + pad, gy + head + pad, gw - pad * 2, gh - head - pad * 2).forEach((r, idx) => {
        const it = r.node.item;
        const x = r.x + 1, y = r.y + 1, w = r.w - 2, h = r.h - 2;
        if (w < 1 || h < 1) return;
        const bg = colorOf(it, idx);
        const e = el('div', 'tm-item' + (it.selectable ? '' : ' keep') + (S.selected.has(it.id) ? ' sel' : '') + (S.focus === it.id ? ' focus' : '') + (w > 220 && h > 90 ? ' big' : ''));
        Object.assign(e.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px', background: bg, color: textOn(bg) });
        e.dataset.id = it.id;
        if (w > 54 && h > 28) {
          const label = S.zoom || w > 150 ? it.name : it.name.replace(/（.*?）/, '');
          const sz = S.sizeBy === 'clean' ? fmt(r.node.value) : (it.selectable && cleanable(it) < it.total ? `${fmt(it.total)} · 可清 ${fmt(cleanable(it))}` : fmt(it.total));
          e.innerHTML = `<div class="tm-name">${esc(label)}</div>${h > 44 ? `<div class="tm-size">${sz}</div>` : ''}`;
        }
        if (it.selectable && w > 30 && h > 28) {
          const c = el('div', 'tm-check', ICON.check);
          c.title = S.selected.has(it.id) ? '移出清理' : '加入清理';
          c.onclick = (ev) => { ev.stopPropagation(); toggle(it.id); };
          e.append(c);
        }
        e.onclick = () => openDetail(it.id);
        e.onmousemove = (ev) => showTip(ev, it);
        e.onmouseleave = hideTip;
        box.append(e);
      });
    }
  }

  function showTip(ev, it) {
    const tip = $('#tip');
    const c = cleanable(it);
    tip.innerHTML = `<div class="tip-title">${esc(it.name)}</div>
      <div class="muted">${esc(toolName(it.tool))} · ${esc(catName(it.category))}</div>
      <div class="tip-row"><span>总占用</span><b>${fmt(it.total)}</b></div>
      ${it.selectable ? `<div class="tip-row"><span>可清理${ageOf(it) ? '（' + AGE_LABEL[AGE_STEPS.indexOf(ageOf(it))] + '）' : ''}</span><b>${fmt(c)}</b></div>` : ''}
      <div class="tip-row"><span>建议</span><b style="display:inline-flex;align-items:center;gap:5px"><span class="dot" style="background:${prioColor(it.priority)}"></span>${prioLabel(it.priority)}</b></div>`;
    tip.hidden = false;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + tw > innerWidth - 8) x = ev.clientX - tw - 14;
    if (y + th > innerHeight - 8) y = ev.clientY - th - 14;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  const hideTip = () => { $('#tip').hidden = true; };

  // ------------------------------------------------------------ 其他区域
  function renderLegend() {
    const lg = $('#legend');
    let html = '';
    if (S.colorBy === 'priority') {
      for (const p of ['1', '2', '3', '4', '5']) {
        const sum = S.items.filter((i) => String(i.priority) === p).reduce((a, i) => a + i.total, 0);
        if (!sum) continue;
        html += `<span title="${esc(S.data.priorities[p].desc)}"><i class="sw" style="background:${prioColor(p)}"></i>${S.data.priorities[p].label}<b class="muted tabular" style="font-weight:500">${fmt(sum)}</b></span>`;
      }
    } else if (S.colorBy === 'tool') {
      const seen = new Set(S.items.filter((i) => !S.zoom || i.tool === S.zoom).map((i) => i.tool));
      for (const t of Object.values(S.tools)) if (seen.has(t.key)) html += `<span><i class="sw" style="background:${t.color}"></i>${esc(t.name)}</span>`;
    } else {
      const seen = new Set(S.items.filter((i) => !S.zoom || i.tool === S.zoom).map((i) => i.category));
      for (const [k, v] of Object.entries(S.data.categories)) if (seen.has(k)) html += `<span><i class="sw" style="background:${CAT_COLORS[k]}"></i>${v}</span>`;
    }
    lg.innerHTML = html;
    const cr = $('#crumbs');
    if (S.zoom) {
      cr.innerHTML = `<button id="crAll">全部</button><span class="sep">/</span><span>${esc(toolName(S.zoom))}</span>`;
      $('#crAll').onclick = () => { S.zoom = null; renderAll(); };
    } else cr.innerHTML = '<span>空间分布</span>';
  }

  function renderStats() {
    const it = S.items;
    const sum = (f) => it.reduce((a, i) => a + f(i), 0);
    const total = sum((i) => i.total);
    const p = (n) => sum((i) => (i.priority === n ? cleanable(i) : 0));
    const selSize = sum((i) => (S.selected.has(i.id) ? cleanable(i) : 0));
    const cards = [
      ['AI 相关总占用', fmt(total), `${it.length} 项 · 用时 ${S.data.elapsed} 秒`, 'var(--primary)'],
      ['可安全清理', fmt(p(1)), '纯缓存，会自动重新生成', prioColor(1)],
      ['建议清理', fmt(p(2)), '旧日志、旧版本、临时文件', prioColor(2)],
      ['谨慎清理', fmt(p(3)), '会话历史、模型，按默认时间', prioColor(3)],
      ['已选择', fmt(selSize), S.selected.size ? `${S.selected.size} 项待清理` : '尚未选择', 'var(--text-4)'],
    ];
    $('#stats').innerHTML = cards.map(([l, n, s, c]) => `<div class="stat"><div class="stat-label"><span class="dot" style="background:${c}"></span>${l}</div><div class="stat-num">${n}</div><div class="stat-sub">${s}</div></div>`).join('');
    const d = S.data.disk;
    if (d && d.total) {
      $('#disk').hidden = false;
      $('#diskLabel').textContent = `${d.drive} 盘`;
      $('#diskFree').textContent = `剩余 ${fmt(d.free)} / ${fmt(d.total)}`;
      $('#diskUsed').style.width = (d.used / d.total) * 100 + '%';
      $('#diskAi').style.width = Math.min(total / d.total, 1) * 100 + '%';
      $('#disk').title = `已用 ${fmt(d.used)}，其中 AI 相关约 ${fmt(total)}（蓝色）`;
    }
  }

  function renderList() {
    const list = $('#list');
    list.innerHTML = '';
    for (const p of ['1', '2', '3', '4', '5']) {
      const items = S.items.filter((i) => String(i.priority) === p);
      if (!items.length) continue;
      const selectable = p <= '3';
      items.sort((a, b) => (selectable ? cleanable(b) - cleanable(a) : 0) || b.total - a.total);
      const grp = el('div', 'grp' + (S.closed.has(p) ? ' closed' : ''));
      const gsum = items.reduce((a, i) => a + (selectable ? cleanable(i) : i.total), 0);
      const head = el('div', 'grp-head', `${ICON.down}<span class="dot" style="background:${prioColor(p)}"></span>${S.data.priorities[p].label}<span class="gsum">${selectable ? '可清理 ' : ''}${fmt(gsum)}</span>`);
      head.onclick = () => { S.closed.has(p) ? S.closed.delete(p) : S.closed.add(p); grp.classList.toggle('closed'); };
      grp.append(head, el('div', 'grp-desc', esc(S.data.priorities[p].desc)));
      for (const it of items) {
        const c = cleanable(it);
        const row = el('div', 'row' + (S.focus === it.id ? ' focus' : ''));
        const t = S.tools[it.tool] || {};
        const age = ageOf(it);
        const size = selectable
          ? `${fmt(c)}${c < it.total ? `<small>共 ${fmt(it.total)}${age ? ' · ' + AGE_LABEL[AGE_STEPS.indexOf(age)] : ''}</small>` : ''}`
          : `${fmt(it.total)}<small>仅查看</small>`;
        row.innerHTML = `<input type="checkbox" ${S.selected.has(it.id) ? 'checked' : ''} ${selectable && c > 0 ? '' : 'disabled'} aria-label="选择">
          <div style="min-width:0"><div class="row-name">${esc(it.name)}</div><div class="row-sub"><i class="tdot" style="background:${t.color}"></i>${esc(t.name || it.tool)} · ${esc(catName(it.category))}${t.running?.length ? ' · <span style="color:var(--warning)">运行中</span>' : ''}</div></div>
          <div class="row-size">${size}</div><span class="go">${ICON.chev}</span>`;
        const cb = row.querySelector('input');
        cb.onclick = (ev) => { ev.stopPropagation(); toggle(it.id); };
        row.onclick = () => openDetail(it.id);
        grp.append(row);
      }
      list.append(grp);
    }
  }

  function renderDetail() {
    const v = $('#viewDetail');
    const it = S.byId[S.focus];
    if (!it) { v.hidden = true; $('#viewList').hidden = false; return; }
    $('#viewList').hidden = true;
    v.hidden = false;
    const t = S.tools[it.tool] || {};
    const age = ageOf(it);
    const c = cleanable(it);
    const sel = S.selected.has(it.id);
    let ageHtml = '';
    if (it.selectable && it.age_by) {
      const max = Math.max(...it.buckets, 1);
      ageHtml = `<div class="age-box">
        <label>只清理 <select class="input" id="ageSel">${AGE_STEPS.map((s, i) => `<option value="${s}" ${s === age ? 'selected' : ''}>${AGE_LABEL[i]}</option>`).join('')}</select> ${it.age_by === 'entry' ? '没有再使用过的内容' : '没有再修改过的文件'}</label>
        <div class="age-bars">${it.buckets.map((b, i) => `<button data-age="${AGE_STEPS[i]}" class="${AGE_STEPS[i] === age ? 'on' : ''}" style="height:${Math.max(4, (b / max) * 100)}%" title="${AGE_LABEL[i]}：${fmt(b)}"></button>`).join('')}</div>
        <div class="age-axis">${AGE_SHORT.map((s) => `<span>${s}</span>`).join('')}</div>
      </div>`;
    }
    const running = t.running?.length ? `<div class="d-note">${ICON.warn}<div>${esc(t.name)} 正在运行（${esc(t.running.join('、'))}）。建议先完全退出再清理，否则被占用的文件会被跳过。</div></div>` : '';
    const note = it.note ? `<div class="d-note info">${ICON.info}<div>${esc(it.note)}</div></div>` : '';
    const top = it.top?.length ? `<div class="d-sec"><h4>${it.mode === 'old_versions' ? '各版本' : '占用最大的内容'}</h4><table class="top">${it.top.map((x) => `<tr class="${x.cleanable || it.mode === 'keep' ? '' : 'keep'}"><td title="${esc(x.name)}">${esc(x.name)}</td><td>${x.cleanable || it.mode === 'keep' ? ago(x.mtime) : (it.mode === 'old_versions' ? '保留（最新）' : '保留')}</td><td>${fmt(x.size)}</td></tr>`).join('')}</table></div>` : '';
    v.innerHTML = `<button class="d-back" id="dBack">${ICON.back}清理建议</button>
      <div class="d-body">
        <div class="d-tool"><span class="dot" style="background:${t.color}"></span>${esc(t.name || it.tool)}</div>
        <div class="d-name">${esc(it.name)}</div>
        <div class="badges"><span><i class="dot" style="background:${prioColor(it.priority)}"></i>${prioLabel(it.priority)}</span><span><i class="dot" style="background:${CAT_COLORS[it.category]}"></i>${esc(catName(it.category))}</span><span class="muted">${it.files.toLocaleString()} 个文件 · 最近 ${ago(it.newest)}</span></div>
        <div class="d-nums"><div class="d-num"><div class="l">总占用</div><div class="v">${fmt(it.total)}</div></div>
          <div class="d-num"><div class="l">${it.selectable ? '可清理' : '可清理'}</div><div class="v" style="color:${it.selectable ? 'var(--text)' : 'var(--text-3)'}">${it.selectable ? fmt(c) : '—'}</div></div></div>
        ${running}
        <div class="d-sec"><h4>这是什么</h4><p>${esc(it.desc)}</p></div>
        <div class="d-sec"><h4>清理后</h4><p>${esc(it.impact)}</p></div>
        ${note}${ageHtml}
        ${top}
        <div class="d-sec"><h4>位置</h4><div class="paths">${it.paths.slice(0, 6).map((p, i) => `<div class="path"><span>${esc(p)}</span><button data-reveal="${i}">打开</button></div>`).join('')}${it.paths.length > 6 ? `<div class="muted" style="font-size:11.5px">另有 ${it.paths.length - 6} 个位置</div>` : ''}</div></div>
        <div class="d-actions">${it.selectable
          ? `<button class="btn ${sel ? '' : 'btn-primary'}" id="dToggle" ${c > 0 || sel ? '' : 'disabled'}>${sel ? '移出清理' : c > 0 ? `加入清理 · ${fmt(c)}` : '当前没有可清理的内容'}</button>`
          : `<button class="btn" disabled>${it.priority === 5 ? '未识别，不提供清理' : '建议保留，不提供清理'}</button>`}</div>
      </div>`;
    $('#dBack').onclick = closeDetail;
    $('#dToggle')?.addEventListener('click', () => toggle(it.id));
    const setAge = (a) => { S.ages[it.id] = a; renderAll(); };
    $('#ageSel')?.addEventListener('change', (e) => setAge(+e.target.value));
    v.querySelectorAll('[data-age]').forEach((b) => (b.onclick = () => setAge(+b.dataset.age)));
    v.querySelectorAll('[data-reveal]').forEach((b) => (b.onclick = () => api('/api/reveal', { id: it.id, index: +b.dataset.reveal }).then((r) => !r.ok && toast('无法打开该位置', 'error'))));
  }

  function renderFoot() {
    const sel = [...S.selected].map((id) => S.byId[id]).filter(Boolean);
    const size = sel.reduce((a, i) => a + cleanable(i), 0);
    $('#selCount').textContent = sel.length ? `已选 ${sel.length} 项` : '未选择';
    $('#selSize').textContent = fmt(size);
    const b = $('#btnClean');
    b.disabled = !sel.length || !size || S.busy;
    b.className = 'btn btn-lg ' + (S.mode === 'delete' ? 'btn-danger-solid' : 'btn-primary');
    b.textContent = S.mode === 'delete' ? '永久删除' : '开始清理';
  }

  function renderAll() {
    if (!S.data) return;
    renderStats();
    renderLegend();
    renderTreemap();
    renderList();
    renderDetail();
    renderFoot();
  }

  // ------------------------------------------------------------ 交互
  function toggle(id) {
    const it = S.byId[id];
    if (!it?.selectable) return;
    if (S.selected.has(id)) S.selected.delete(id);
    else if (cleanable(it) > 0) S.selected.add(id);
    renderAll();
  }
  function openDetail(id) { S.focus = id; renderAll(); }
  function closeDetail() { S.focus = null; renderAll(); }

  function quickSelect(level) {
    S.selected.clear();
    if (level) for (const it of S.items) if (it.selectable && it.priority <= level && cleanable(it) > 0) S.selected.add(it.id);
    renderAll();
  }

  function setSeg(id, value) {
    document.querySelectorAll(`#${id} button`).forEach((b) => b.classList.toggle('active', b.dataset.v === value));
  }

  function toast(msg, type = '') {
    const t = el('div', 'toast' + (type ? ' toast-' + type : ''), esc(msg));
    $('#toasts').append(t);
    requestAnimationFrame(() => t.classList.add('show'));
    setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 400); }, 2800);
  }

  function modal(html, onReady) {
    const ov = el('div', 'modal-overlay');
    const m = el('div', 'modal confirm', html);
    ov.append(m);
    document.body.append(ov);
    const close = () => { ov.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    ov.addEventListener('mousedown', (e) => { if (e.target === ov) close(); });
    onReady(m, close);
  }

  function confirmClean() {
    const sel = [...S.selected].map((id) => S.byId[id]).filter((i) => i && cleanable(i) > 0);
    if (!sel.length) return;
    const size = sel.reduce((a, i) => a + cleanable(i), 0);
    const del = S.mode === 'delete';
    const cautious = sel.filter((i) => i.priority === 3);
    const running = [...new Set(sel.map((i) => i.tool))].map((k) => S.tools[k]).filter((t) => t?.running?.length);
    const warns = [];
    if (cautious.length) warns.push(`包含 <b>${cautious.length} 项谨慎清理</b>的内容（${cautious.map((i) => esc(i.name)).join('、')}），删除后无法找回或需要重新下载。`);
    if (running.length) warns.push(`<b>${running.map((t) => esc(t.name)).join('、')}</b> 正在运行，建议先退出，否则被占用的文件会被跳过。`);
    if (!del) warns.push('移到回收站后，需要<b>清空回收站</b>才会真正释放磁盘空间。');
    modal(`<div class="c-icon ${del ? 'danger' : ''}">${ICON.trash}</div>
      <div class="c-title">${del ? '永久删除' : '移到回收站'} ${sel.length} 项，共 ${fmt(size)}？</div>
      <div class="modal-body">
        <div class="c-items">${sel.map((i) => `<div class="c-item"><span class="dot" style="background:${prioColor(i.priority)}"></span><span class="n">${esc(toolName(i.tool))} · ${esc(i.name)}${ageOf(i) ? `（${AGE_LABEL[AGE_STEPS.indexOf(ageOf(i))]}）` : ''}</span><span class="s">${fmt(cleanable(i))}</span></div>`).join('')}</div>
        ${warns.map((w) => `<div class="c-warn">${w}</div>`).join('')}
      </div>
      <div class="modal-footer"><button class="btn" data-x>取消</button><button class="btn ${del ? 'btn-danger-solid' : 'btn-primary'}" data-ok>${del ? '永久删除' : '移到回收站'}</button></div>`,
    (m, close) => {
      m.querySelector('[data-x]').onclick = close;
      const ok = m.querySelector('[data-ok]');
      ok.focus();
      ok.onclick = () => { close(); runClean(sel); };
    });
  }

  async function runClean(sel) {
    const r = await api('/api/clean', { mode: S.mode, items: sel.map((i) => ({ id: i.id, age: ageOf(i) })) });
    if (!r.ok) return toast('正在扫描或清理中，请稍后', 'error');
    const st = await waitIdle('正在清理…');
    await loadResult();
    const rep = st.clean.report;
    if (!rep) return;
    for (const x of rep.items) if (!x.failed) S.selected.delete(x.id);
    renderAll();
    const failed = rep.items.filter((x) => x.failed);
    modal(`<div class="c-icon ${failed.length ? '' : 'ok'}">${failed.length ? ICON.info : ICON.ok}</div>
      <div class="c-title">${rep.mode === 'delete' ? '已释放' : '已移到回收站'} ${fmt(rep.freed)}</div>
      <div class="modal-body">
        <div class="c-items">${rep.items.map((x) => `<div class="c-item"><span class="n">${esc(x.name)}${x.failed ? `<div class="e">${x.failed} 个文件被占用或无权限，已跳过</div>` : ''}</span><span class="s">${fmt(x.freed)}</span></div>`).join('')}</div>
        ${failed.length ? `<div class="c-warn">部分文件没有删除，通常是对应软件正在运行。退出软件后可以再清理一次。</div><div class="c-errs">${esc(failed.flatMap((x) => x.errors).slice(0, 12).join('\n'))}</div>` : ''}
        ${rep.mode !== 'delete' ? '<div class="c-warn">清空回收站后才会真正释放这部分 C 盘空间。</div>' : ''}
      </div>
      <div class="modal-footer"><button class="btn btn-primary" data-x>完成</button></div>`,
    (m, close) => { m.querySelector('[data-x]').onclick = close; });
  }

  // ------------------------------------------------------------ 扫描
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitIdle(title) {
    S.busy = true;
    renderFoot();
    const ov = $('#overlay');
    ov.hidden = false;
    $('#ovTitle').textContent = title;
    let st;
    for (;;) {
      st = await api('/api/status');
      const job = st.clean.phase === 'cleaning' ? st.clean : st.scan;
      const pct = job.total ? (job.done / job.total) * 100 : 0;
      $('#ovBar').style.width = pct + '%';
      $('#ovSub').textContent = job.current ? `${job.current}（${job.done}/${job.total}）` : `${job.done}/${job.total}`;
      if (st.clean.phase === 'cleaning') $('#ovTitle').textContent = '正在清理…';
      else if (title === '正在清理…') $('#ovTitle').textContent = '正在重新统计…';
      if (!st.busy) break;
      await sleep(250);
    }
    ov.hidden = true;
    S.busy = false;
    return st;
  }

  async function loadResult() {
    const data = await api('/api/result');
    if (!data.items) return;
    S.data = data;
    S.items = data.items;
    S.byId = Object.fromEntries(data.items.map((i) => [i.id, i]));
    S.tools = Object.fromEntries(data.tools.map((t) => [t.key, t]));
    for (const id of [...S.selected]) if (!S.byId[id] || cleanable(S.byId[id]) <= 0) S.selected.delete(id);
    if (S.focus && !S.byId[S.focus]) S.focus = null;
    if (S.zoom && !S.items.some((i) => i.tool === S.zoom)) S.zoom = null;
    renderAll();
  }

  async function scan(first) {
    await api('/api/scan', {});
    await waitIdle('正在扫描 AI 工具的数据…');
    await loadResult();
    if (first && !S.selected.size) {
      for (const it of S.items) if (it.priority === 1 && cleanable(it) > 0) S.selected.add(it.id);
      renderAll();
    }
  }

  // ------------------------------------------------------------ 主题与事件
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    $('#btnTheme').innerHTML = t === 'dark' ? ICON.sun : ICON.moon;
    store.set('theme', t);
    renderAll();
  }

  function bind() {
    $('#btnScan').onclick = () => !S.busy && scan(false);
    $('#btnTheme').onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    $('#btnClean').onclick = confirmClean;
    document.querySelectorAll('#segColor button').forEach((b) => (b.onclick = () => { S.colorBy = b.dataset.v; store.set('colorBy', S.colorBy); setSeg('segColor', S.colorBy); renderAll(); }));
    document.querySelectorAll('#segSize button').forEach((b) => (b.onclick = () => { S.sizeBy = b.dataset.v; store.set('sizeBy', S.sizeBy); setSeg('segSize', S.sizeBy); renderAll(); }));
    document.querySelectorAll('#segMode button').forEach((b) => (b.onclick = () => { S.mode = b.dataset.v; setSeg('segMode', S.mode); $('#segMode').classList.toggle('seg-danger', S.mode === 'delete'); renderFoot(); }));
    document.querySelectorAll('[data-quick]').forEach((b) => (b.onclick = () => quickSelect(+b.dataset.quick)));
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || document.querySelector('.modal-overlay')) return;
      if (S.focus) closeDetail(); else if (S.zoom) { S.zoom = null; renderAll(); }
    });
    let timer;
    new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(renderTreemap, 60); }).observe($('#treemap'));
    setSeg('segColor', S.colorBy);
    setSeg('segSize', S.sizeBy);
  }

  const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = store.get('theme', prefersDark ? 'dark' : 'light');
  $('#btnTheme').innerHTML = document.documentElement.dataset.theme === 'dark' ? ICON.sun : ICON.moon;
  bind();
  (async () => {
    // 刷新页面时，5 分钟内的扫描结果直接复用
    const st = await api('/api/status');
    if (st.busy) await waitIdle('正在扫描 AI 工具的数据…');
    const cached = await api('/api/result');
    if (cached.items && Date.now() / 1000 - cached.scanned_at < 300) {
      await loadResult();
      for (const it of S.items) if (it.priority === 1 && cleanable(it) > 0) S.selected.add(it.id);
      $('#overlay').hidden = true;
      renderAll();
    } else await scan(true);
  })().catch((e) => { $('#ovTitle').textContent = '连接失败'; $('#ovSub').textContent = String(e); });
})();
