/* 离线面板只从内嵌数据读取；业务文字一律用 textContent 写入，不执行备注，也不发外部请求。 */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('panel-data').textContent);

  // 状态顺序即图例顺序；颜色取自样式变量，深浅主题自动切换。
  const STATES = {
    stable: '稳定通过', checked: '待验证稳定性', developing: '开发中', failed: '当前检查失败',
    stale: '证据过期', unknown: '缺少证据', skeleton: '骨架', planned: '计划',
  };
  const KINDS = { workflow: '流程包', capability: '能力包', library: '工具包', unknown: '未分类' };
  const RULE_STATES = { inferred: '推定', adopted: '采纳', confirmed: '已确认', retired: '已废止' };
  const RISKS = { high: '高风险', medium: '中风险', low: '低风险' };
  const TASK_STATES = { active: '进行中', incomplete: '未完成', complete: '已完成', completed: '已完成', stale: '需要更新', closed: '已关闭' };
  const EDGES = { actual: '实际调用', planned: '计划依赖', library: '使用工具包', exception: '登记的只读例外', invalid: '违反依赖方向' };
  const NODE_W = 228, NODE_H = 74;

  const $ = id => document.getElementById(id);
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const el = (tag, text, klass) => { const node = document.createElement(tag); if (text !== undefined && text !== null) node.textContent = text; if (klass) node.className = klass; return node; };
  const svg = (tag, attrs = {}) => { const node = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value)); return node; };
  const chip = (text, tone) => el('span', text, 'chip' + (tone ? ' ' + tone : ''));
  const list = value => Array.isArray(value) ? value : value ? [value] : [];
  const short = (text, size) => text.length > size ? text.slice(0, size - 1) + '…' : text;
  const tail = path => String(path || '').split('/').slice(-2).join('/');
  const stateTone = state => ({ stable: 'good', checked: 'good', developing: 'warn', failed: 'bad', stale: 'info' })[state] || '';
  const nodeById = Object.fromEntries(data.nodes.map(node => [node.id, node]));

  // 时间写成"几分钟前"，悬停可见完整时间。
  function ago(value) {
    if (!value) return '时间未知';
    const seconds = (Date.now() - new Date(value).getTime()) / 1000;
    if (!Number.isFinite(seconds)) return '时间未知';
    if (seconds < 60) return '刚刚';
    if (seconds < 3600) return Math.round(seconds / 60) + ' 分钟前';
    if (seconds < 86400) return Math.round(seconds / 3600) + ' 小时前';
    return Math.round(seconds / 86400) + ' 天前';
  }
  const duration = seconds => typeof seconds !== 'number' ? '未知' : seconds >= 90 ? (seconds / 60).toFixed(1) + ' 分钟' : seconds.toFixed(1) + ' 秒';
  function scopeText(scope) {
    if (!scope) return '范围未知';
    if (scope.kind === 'all') return '完整检查';
    if (scope.kind === 'quick') return '快速检查';
    const modules = list(scope.modules || scope.module);
    return modules.length ? '检查 ' + modules.join('、') : '局部检查';
  }
  function counts(value) {
    if (!value) return '';
    const parts = [];
    if (value.passed) parts.push(value.passed + ' 通过');
    if (value.failed) parts.push(value.failed + ' 失败');
    if (value.skipped) parts.push(value.skipped + ' 跳过');
    return parts.join('，') || '没有测试';
  }

  // 顶栏的状态条：按包统计，一眼看出整体完成度。
  function overall() {
    const root = $('overall'), bar = el('div', undefined, 'bar'), keys = el('div', undefined, 'keys');
    const total = data.nodes.length || 1;
    for (const state of Object.keys(STATES)) {
      const count = data.nodes.filter(node => node.state === state).length;
      if (!count) continue;
      const part = el('span'); part.style.width = (count / total * 100) + '%';
      part.style.background = css('--' + state + '-line'); part.title = STATES[state] + ' ' + count + ' 个包';
      bar.append(part);
      const key = el('span'); key.append(el('b', String(count)), document.createTextNode(STATES[state])); keys.append(key);
    }
    root.replaceChildren(bar, keys);
  }

  // ===== 项目图 =====
  const view = { x: 0, y: 0, k: 1, width: 1, height: 1 };
  let selected = null, currentLine = '';

  function applyView() { $('viewport').setAttribute('transform', `translate(${view.x},${view.y}) scale(${view.k})`); }
  function fit(event) {
    const loose = event && event.type === 'click';
    const box = $('graph').getBoundingClientRect();
    if (!box.width) return;
    const top = 64, bottom = 56, pad = 28;
    const k = Math.min(1.25, (box.width - pad * 2) / view.width, (box.height - top - bottom) / view.height);
    // 字太小就没法读，图比画布大时保持可读的比例，从左上角开始，拖动查看其余部分。
    view.k = Math.max(loose ? 0.2 : 0.72, k);
    view.x = Math.max(pad, (box.width - view.width * view.k) / 2);
    view.y = top + Math.max(0, (box.height - top - bottom - view.height * view.k) / 2);
    applyView();
  }
  function zoom(factor, cx, cy) {
    const box = $('graph').getBoundingClientRect();
    const x = cx ?? box.width / 2, y = cy ?? box.height / 2;
    const k = Math.min(3, Math.max(0.15, view.k * factor));
    view.x = x - (x - view.x) * (k / view.k); view.y = y - (y - view.y) * (k / view.k); view.k = k;
    applyView();
  }

  // 折线点转成平滑曲线，避免连线像电路图一样生硬。
  function curve(points) {
    if (points.length < 3) return 'M' + points.map(p => p.x + ',' + p.y).join(' L');
    let d = `M${points[0].x},${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i - 1] || points[i], p1 = points[i], p2 = points[i + 1], p3 = points[i + 2] || p2;
      d += ` C${p1.x + (p2.x - p0.x) / 6},${p1.y + (p2.y - p0.y) / 6} ${p2.x - (p3.x - p1.x) / 6},${p2.y - (p3.y - p1.y) / 6} ${p2.x},${p2.y}`;
    }
    return d;
  }

  function visibleNodes() {
    const query = $('search').value.trim().toLowerCase();
    return data.nodes.filter(node => (!currentLine || node.line === currentLine) && (!query || (node.id + ' ' + node.title).toLowerCase().includes(query)));
  }

  function graph() {
    const nodes = visibleNodes(), root = $('viewport');
    root.replaceChildren();
    $('empty').hidden = nodes.length > 0;
    if (!nodes.length) return;
    const names = new Set(nodes.map(node => node.id));
    const edges = data.edges.filter(edge => names.has(edge.source) && names.has(edge.target) && edge.source !== edge.target);
    const lines = [...new Set(nodes.map(node => node.line))];
    const clustered = !currentLine && lines.length > 1;
    // 横排和竖排各算一次，选能放得更大的那种，避免长链把字缩到看不清。
    const build = direction => {
      const result = new dagre.graphlib.Graph({ multigraph: true, compound: true })
        .setGraph({ rankdir: direction, nodesep: direction === 'LR' ? 22 : 30, ranksep: direction === 'LR' ? 64 : 56, marginx: 20, marginy: 20 })
        .setDefaultEdgeLabel(() => ({}));
      if (clustered) lines.forEach(line => result.setNode('line:' + line, { label: line, paddingTop: 34, paddingLeft: 16, paddingRight: 16, paddingBottom: 16 }));
      nodes.forEach(node => { result.setNode(node.id, { width: NODE_W, height: NODE_H }); if (clustered) result.setParent(node.id, 'line:' + node.line); });
      edges.forEach((edge, index) => result.setEdge(edge.source, edge.target, { weight: edge.kind === 'actual' ? 2 : 1 }, String(index)));
      dagre.layout(result);
      return result;
    };
    const area = $('graph').getBoundingClientRect();
    const scale = candidate => Math.min((area.width - 56) / candidate.graph().width, (area.height - 120) / candidate.graph().height);
    const wide = build('LR'), tall = build('TB');
    const layout = scale(tall) > scale(wide) * 1.15 ? tall : wide;
    view.width = Math.max(300, layout.graph().width); view.height = Math.max(200, layout.graph().height);

    if (clustered) lines.forEach(line => {
      const box = layout.node('line:' + line);
      if (!box || !box.width) return;
      const group = svg('g', { class: 'cluster' });
      group.append(svg('rect', { x: box.x - box.width / 2, y: box.y - box.height / 2, width: box.width, height: box.height, rx: 14 }));
      const label = svg('text', { x: box.x - box.width / 2 + 16, y: box.y - box.height / 2 + 22 }); label.textContent = line;
      group.append(label); root.append(group);
    });

    const defs = svg('defs');
    for (const kind of Object.keys(EDGES)) {
      const marker = svg('marker', { id: 'arrow-' + kind, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
      marker.append(svg('path', { d: 'M0,1 L9,5 L0,9 z', fill: css('--edge' + (kind === 'actual' ? '' : '-' + kind)) || css('--edge') }));
      defs.append(marker);
    }
    root.append(defs);

    const edgeElements = [];
    edges.forEach((edge, index) => {
      const points = layout.edge({ v: edge.source, w: edge.target, name: String(index) }).points;
      const path = svg('path', { d: curve(points), class: 'edge ' + edge.kind, 'marker-end': `url(#arrow-${edge.kind})` });
      if (edge.kind === 'actual' && edge.count > 1) path.style.strokeWidth = Math.min(4, 1.2 + edge.count * 0.6);
      path.dataset.source = edge.source; path.dataset.target = edge.target;
      tip(path, () => `${nodeById[edge.source]?.title || edge.source} → ${nodeById[edge.target]?.title || edge.target}\n${EDGES[edge.kind] || edge.kind}，${edge.count} 个操作`);
      root.append(path); edgeElements.push(path);
    });

    nodes.forEach(node => {
      const p = layout.node(node.id);
      const group = svg('g', { class: 'node' + (node.id === selected ? ' selected' : ''), transform: `translate(${p.x - NODE_W / 2},${p.y - NODE_H / 2})`, tabindex: 0, role: 'button', 'aria-label': `${node.title}，${STATES[node.state]}` });
      group.dataset.id = node.id;
      if (node.size?.suggest_split) group.append(svg('rect', { class: 'split', x: -5, y: -5, width: NODE_W + 10, height: NODE_H + 10, rx: 14 }));
      const box = svg('rect', { class: 'box', width: NODE_W, height: NODE_H, rx: 10, fill: css('--' + node.state + '-fill') || css('--paper'), stroke: css('--' + node.state + '-line') });
      if (node.state === 'planned') box.setAttribute('stroke-dasharray', '6 4');
      group.append(box);
      const kind = svg('text', { class: 'kind', x: 14, y: 21, fill: css('--' + node.state + '-line') }); kind.textContent = KINDS[node.kind] || KINDS.unknown; group.append(kind);
      const title = svg('text', { class: 'title', x: 14, y: 41 }); title.textContent = short(node.title, 13); group.append(title);
      const id = svg('text', { class: 'id', x: 14, y: 60 }); id.textContent = short(node.id, 28); group.append(id);
      const state = svg('text', { class: 'meta', x: NODE_W - 14, y: 21, 'text-anchor': 'end' }); state.textContent = STATES[node.state]; group.append(state);
      let badge = NODE_W - 16;
      if (node.flaky) { const flash = svg('text', { x: badge, y: 60, 'text-anchor': 'end', 'font-size': 13, fill: css('--developing-line') }); flash.textContent = '⚡'; group.append(flash); badge -= 18; }
      if (node.pending_confirmation) group.append(svg('circle', { cx: badge - 3, cy: 56, r: 5, fill: css('--confirm') }));
      tip(group, () => [node.title + '（' + node.id + '）', STATES[node.state] + '：' + (node.reason || ''), node.pending_confirmation ? '有高风险规则等你确认' : '', node.flaky ? '同一份代码检查时过时不过' : '', node.size?.suggest_split ? '规模超过建议值，建议评估拆分' : ''].filter(Boolean).join('\n'));
      group.addEventListener('click', event => { event.stopPropagation(); select(node.id); });
      group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(node.id); } });
      group.addEventListener('mouseenter', () => focus(node.id, edgeElements));
      group.addEventListener('mouseleave', () => focus(null, edgeElements));
      root.append(group);
    });
    fit();
  }

  // 悬停一个包时，只保留它和直接相连的包与连线。
  function focus(id, edgeElements) {
    const svgRoot = $('graph');
    if (!id) { svgRoot.classList.remove('focusing'); return; }
    const near = new Set([id]);
    edgeElements.forEach(path => { const hit = path.dataset.source === id || path.dataset.target === id; path.classList.toggle('near', hit); if (hit) { near.add(path.dataset.source); near.add(path.dataset.target); } });
    svgRoot.querySelectorAll('.node').forEach(node => node.classList.toggle('near', near.has(node.dataset.id)));
    svgRoot.classList.add('focusing');
  }

  function select(id) {
    selected = id;
    $('graph').querySelectorAll('.node').forEach(node => node.classList.toggle('selected', node.dataset.id === id));
    id ? detail(nodeById[id]) : overview();
  }

  // 拖动平移、滚轮缩放；点空白处回到项目概况。
  function interactions() {
    const canvas = $('canvas'), graphRoot = $('graph');
    let drag = null;
    graphRoot.addEventListener('pointerdown', event => { if (event.target.closest('.node')) return; drag = { x: event.clientX - view.x, y: event.clientY - view.y, moved: false }; canvas.classList.add('dragging'); graphRoot.setPointerCapture(event.pointerId); });
    graphRoot.addEventListener('pointermove', event => { if (!drag) return; view.x = event.clientX - drag.x; view.y = event.clientY - drag.y; drag.moved = true; applyView(); });
    graphRoot.addEventListener('pointerup', () => { if (drag && !drag.moved) select(null); drag = null; canvas.classList.remove('dragging'); });
    graphRoot.addEventListener('wheel', event => { event.preventDefault(); const box = graphRoot.getBoundingClientRect(); zoom(Math.exp(-event.deltaY * 0.0015), event.clientX - box.left, event.clientY - box.top); }, { passive: false });
    $('zoom-in').addEventListener('click', () => zoom(1.2));
    $('zoom-out').addEventListener('click', () => zoom(1 / 1.2));
    $('fit').addEventListener('click', fit);
    $('search').addEventListener('input', graph);
    window.addEventListener('resize', fit);
  }

  function lineFilter() {
    const root = $('line-filter');
    const lines = ['', ...new Set(data.nodes.map(node => node.line))];
    root.replaceChildren(...lines.map(line => {
      const button = el('button', line || '全部业务线');
      button.setAttribute('role', 'tab'); button.setAttribute('aria-selected', String(line === currentLine));
      button.addEventListener('click', () => setLine(line));
      return button;
    }));
  }
  function setLine(line) {
    currentLine = line;
    $('line-filter').querySelectorAll('button').forEach((button, index) => button.setAttribute('aria-selected', String((index === 0 ? '' : button.textContent) === line)));
    graph();
    document.getElementById('map').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function legend() {
    const root = $('legend');
    for (const [state, label] of Object.entries(STATES)) {
      if (!data.nodes.some(node => node.state === state)) continue;
      const item = el('span', undefined, 'item'), swatch = el('i', undefined, 'sw');
      swatch.style.background = css('--' + state + '-fill'); swatch.style.borderColor = css('--' + state + '-line');
      if (state === 'planned') swatch.style.borderStyle = 'dashed';
      item.append(swatch, document.createTextNode(label)); root.append(item);
    }
    const kinds = new Set(data.edges.map(edge => edge.kind));
    if (kinds.size) root.append(el('span', undefined, 'sep'));
    for (const [kind, label] of Object.entries(EDGES)) {
      if (!kinds.has(kind)) continue;
      const item = el('span', undefined, 'item'), line = el('i', undefined, 'ln');
      line.style.borderColor = css('--edge' + (kind === 'actual' ? '' : '-' + kind));
      if (kind === 'planned') line.style.borderTopStyle = 'dashed';
      if (kind === 'exception') line.style.borderTopStyle = 'dotted';
      item.append(line, document.createTextNode(label)); root.append(item);
    }
  }

  // ===== 检查器 =====
  function overview() {
    const root = $('detail');
    root.replaceChildren();
    const head = el('div', undefined, 'head'); head.append(el('h2', '项目概况'), el('p', `${data.nodes.length} 个包，${data.edges.filter(edge => edge.kind !== 'planned').length} 条实际依赖。点击图中的包查看详情。`, 'reason'));
    root.append(head, el('h3', '包的状态'));
    for (const [state, label] of Object.entries(STATES)) {
      const count = data.nodes.filter(node => node.state === state).length;
      if (!count) continue;
      const row = el('div', undefined, 'overview-state link'), swatch = el('i', undefined, 'sw');
      swatch.style.background = css('--' + state + '-fill'); swatch.style.borderColor = css('--' + state + '-line');
      row.append(swatch, document.createTextNode(label), el('em', count + ' 个'));
      row.addEventListener('click', () => { const first = data.nodes.find(node => node.state === state); if (first) select(first.id); });
      root.append(row);
    }
    const flags = [];
    data.nodes.filter(node => node.state === 'failed').forEach(node => flags.push(['--failed-line', node.title + '：' + node.reason, node.id]));
    data.nodes.filter(node => node.pending_confirmation).forEach(node => flags.push(['--confirm', node.title + '有高风险规则等你确认', node.id]));
    (data.git?.overlaps || []).forEach(overlap => flags.push(['--developing-line', `${overlap.package} 同时被 ${overlap.branches.length} 个分支修改，合并时要核对`, overlap.package]));
    data.nodes.filter(node => node.size?.suggest_split).forEach(node => flags.push(['--split', node.title + '建议评估拆分', node.id]));
    if (flags.length) {
      root.append(el('h3', '需要留意'));
      flags.slice(0, 8).forEach(([color, text, id]) => {
        const row = el('div', undefined, 'flag link'), dot = el('i'); dot.style.background = css(color);
        row.append(dot, el('span', text)); if (nodeById[id]) row.addEventListener('click', () => select(id)); root.append(row);
      });
    }
  }

  function detail(node) {
    const root = $('detail');
    root.replaceChildren();
    const head = el('div', undefined, 'head');
    head.append(el('h2', node.title), el('code', node.id));
    const chips = el('div', undefined, 'chips');
    chips.append(chip(STATES[node.state], stateTone(node.state)), chip(KINDS[node.kind] || KINDS.unknown), chip('业务线 · ' + node.line));
    if (node.flaky) chips.append(chip('⚡ 检查不稳定', 'warn'));
    if (node.pending_confirmation) chips.append(chip('有规则等你确认', 'confirm'));
    head.append(chips, el('p', node.reason, 'reason'));
    root.append(head);

    root.append(el('h3', '操作与步骤'));
    const operations = node.operations || [];
    if (!operations.length) root.append(el('p', node.state === 'planned' ? '计划中的操作：' + (node.planned_operations || []).join('、') || '还没有设计操作。' : '没有公开操作。', 'quiet'));
    operations.forEach(operation => {
      const block = el('div', undefined, 'op');
      const top = el('div', undefined, 'row'); top.append(el('strong', operation.title), chip(operation.implementation === 'real' ? '真实实现' : '模拟骨架', operation.implementation === 'real' ? 'good' : ''));
      block.append(top);
      (operation.steps || []).forEach((step, index) => {
        const row = el('div', undefined, 'step'), body = el('div');
        body.append(el('span', step.title || step.name), document.createTextNode(step.simulated ? ' · 模拟' : ''), el('br'), el('code', step.source));
        row.append(el('span', String(index + 1), 'n'), body); block.append(row);
      });
      root.append(block);
    });

    root.append(el('h3', '业务规则'));
    if (!(node.rules || []).length) root.append(el('p', '规则账本里还没有这个包的规则。', 'quiet'));
    (node.rules || []).forEach(rule => {
      const row = el('div', undefined, 'row'), tags = el('span');
      tags.append(chip(RISKS[rule.risk] || rule.risk, rule.risk === 'high' ? 'bad' : ''), document.createTextNode(' '), chip(RULE_STATES[rule.state] || rule.state, rule.state === 'confirmed' ? 'good' : rule.state === 'retired' ? '' : 'confirm'));
      row.append(el('code', rule.id), tags); root.append(row);
    });

    root.append(el('h3', '最近检查'));
    const records = node.recent_records || [];
    if (!records.length) root.append(el('p', '还没有正式检查记录。', 'quiet'));
    records.slice(0, 5).forEach(record => {
      const row = el('div', undefined, 'row'), left = el('div');
      left.append(el('span', scopeText(record.scope) + (record.current_module ? '' : '（旧代码）')), el('br'));
      const suites = (record.suites || []).map(suite => suite.database + ' ' + counts(suite.counts)).join('；');
      left.append(el('small', ago(record.finished_at) + ' · ' + duration(record.elapsed_seconds) + (suites ? ' · ' + suites : '')));
      left.lastChild.style.color = css('--muted');
      row.append(left, chip(record.passed ? '通过' : '失败', record.passed ? 'good' : 'bad'));
      root.append(row);
    });

    if (node.size) {
      root.append(el('h3', '规模'));
      const limits = node.size.thresholds || {};
      [['代码行数', 'lines'], ['步骤数', 'steps'], ['依赖数', 'dependencies']].forEach(([label, key]) => {
        const value = node.size[key] ?? 0, limit = limits[key];
        const row = el('div'); const top = el('div', undefined, 'row'); top.style.borderBottom = '0'; top.style.paddingBottom = '0';
        top.append(el('span', label), el('span', limit ? `${value} / 建议 ${limit} 以内` : String(value)));
        row.append(top);
        if (limit) { const meter = el('div', undefined, 'meter'), bar = el('span'); bar.style.width = Math.min(100, value / limit * 100) + '%'; if (value > limit) bar.className = 'over'; meter.append(bar); row.append(meter); }
        root.append(row);
      });
    }
    if ((node.duplicates || []).length) {
      root.append(el('h3', '可能重复的实现'));
      node.duplicates.forEach(hint => { const entry = el('div', undefined, 'entry'); entry.append(el('span', hint.meaning)); hint.locations.forEach(item => entry.append(el('br'), el('code', item.source))); root.append(entry); });
    }
    if (node.note) root.append(el('h3', '备注（不影响颜色）'), el('div', node.note, 'note'));
  }

  // ===== 业务进度 =====
  function progress() {
    const root = $('line-progress');
    root.replaceChildren();
    if (!data.lines.length) { root.append(el('p', '项目图里还没有业务线。', 'quiet')); return; }
    const parts = [['稳定', '--stable-line'], ['已实现', '--checked-line'], ['骨架', '--skeleton-line'], ['计划', '--planned-line']];
    data.lines.forEach(line => {
      const nodes = data.nodes.filter(node => line.packages.includes(node.id));
      let stable = 0, real = 0, skeleton = 0, planned = 0;
      nodes.forEach(node => {
        const operations = node.operations || [];
        if (!operations.length) { planned += (node.planned_operations || []).length; return; }
        operations.forEach(operation => { if (operation.implementation !== 'real') skeleton++; else if (node.state === 'stable') stable++; else real++; });
      });
      const total = stable + real + skeleton + planned;
      const librariesOnly = nodes.length && nodes.every(node => node.kind === 'library');
      const rules = nodes.flatMap(node => node.rules || []);
      const confirmed = rules.filter(rule => rule.state === 'confirmed').length;
      const row = el('div', undefined, 'line-row'), name = el('div', undefined, 'name');
      name.append(document.createTextNode(line.name), el('small', nodes.length + ' 个包'));
      const stack = el('div', undefined, 'stack');
      [stable, real, skeleton, planned].forEach((value, index) => { if (!value) return; const part = el('span'); part.style.width = (value / total * 100) + '%'; part.style.background = css(parts[index][1]); part.title = parts[index][0] + ' ' + value + ' 个操作'; stack.append(part); });
      const facts = librariesOnly ? el('div', '工具包没有公开操作，按使用它的包统计', 'facts') : el('div', `${total ? Math.round(stable / total * 100) : 0}% 稳定 · ${stable + real}/${total} 已实现 · 规则确认 ${confirmed}/${rules.length}`, 'facts');
      row.append(name, stack, facts);
      row.addEventListener('click', () => setLine(line.name));
      root.append(row);
    });
    const keys = el('div', undefined, 'facts'); keys.style.padding = '8px 0 2px'; keys.style.textAlign = 'left';
    keys.textContent = '分段颜色：' + parts.map(part => part[0]).join(' · ') + '（按操作计数）。点击一行，只看这条业务线的项目图。';
    root.append(keys);
  }

  // ===== 待办三栏 =====
  function entry(title, side, lines, options = {}) {
    const box = el('div', undefined, 'entry' + (options.alert ? ' alert' : '') + (options.target ? ' link' : ''));
    const top = el('div', undefined, 'line1'); top.append(el('span', title)); if (side) top.append(side);
    box.append(top);
    lines.filter(Boolean).forEach(line => box.append(typeof line === 'string' ? el('p', line) : line));
    if (options.target && nodeById[options.target]) box.addEventListener('click', () => { select(options.target); document.getElementById('map').scrollIntoView({ behavior: 'smooth' }); });
    return box;
  }
  function group(root, title, items, empty) {
    root.append(el('div', title, 'group-title'));
    if (!items.length) { root.append(el('p', empty, 'quiet')); return; }
    items.forEach(item => root.append(item));
  }
  const packageOf = id => String(id || '').split('.')[0];

  function pending() {
    const root = $('pending'); root.replaceChildren();
    const attention = data.attention || {};
    group(root, '规则等你确认', (attention.rules || []).map(rule => entry(rule.id, chip(RISKS[rule.risk] || rule.risk, rule.risk === 'high' ? 'bad' : ''),
      [`目前是"${RULE_STATES[rule.state] || rule.state}"，第 ${rule.revision} 版。用 dev rules confirm_sheet 生成确认单。`], { target: packageOf(rule.id) })), '没有等待确认的规则。');
    group(root, '契约修改请求', (attention.contract_requests || []).map(request => entry(request.package, chip(request.state === 'open' ? '待处理' : request.state, 'warn'),
      [request.reason, request.suggestion ? '建议：' + request.suggestion : ''], { target: request.package })), '没有子代理提出契约修改。');
    group(root, '收工审查单', (attention.reviews || []).map(review => {
      const task = (data.tasks || []).find(item => item.id === review.task);
      const outside = list(review.outside);
      return entry(task ? task.package : '任务 ' + short(review.task, 10), chip(TASK_STATES[review.state] || review.state, review.state === 'complete' ? 'good' : 'warn'),
        [...list(review.problems), outside.length ? '超出任务范围的改动：' + outside.map(tail).join('、') : ''], { alert: list(review.problems).length > 0, target: task?.package });
    }), '没有待看的审查单。');
  }

  function work() {
    const root = $('work'); root.replaceChildren();
    const git = data.git || {};
    group(root, '任务', (data.tasks || []).map(task => entry(task.package, chip(TASK_STATES[task.state] || task.state, task.state === 'complete' ? 'good' : task.state === 'active' ? 'info' : 'warn'),
      [`${ago(task.created_at)}开工 · 分支 ${task.branch || '未知'} · 样例 ${list(task.cases).join('、') || '未指定'}`, ...list(task.reasons)], { alert: list(task.reasons).length > 0, target: task.package })), '没有任务卡。');
    const overlaps = (git.overlaps || []).map(overlap => entry(overlap.package + ' 有冲突风险', chip(overlap.branches.length + ' 个分支', 'bad'), ['同时被 ' + overlap.branches.join('、') + ' 修改，合并时要先核对。'], { alert: true, target: overlap.package }));
    const branches = (git.branches || []).filter(branch => branch.name !== git.base || branch.changed_files).map(branch => {
      const chips = el('div', undefined, 'chips'); list(branch.packages).forEach(name => chips.append(chip(name)));
      if (branch.framework_changed) chips.append(chip('改了框架', 'warn'));
      return entry(branch.name, el('span', branch.changed_files + ' 个文件', 'chip'), [list(branch.packages).length || branch.framework_changed ? chips : '没有改动业务包']);
    });
    group(root, '分支', [...overlaps, ...branches], '除主干外没有别的分支。');
    group(root, '工作树', (git.worktrees || []).map(tree => {
      const check = tree.latest_check;
      const text = check ? `${scopeText(check.scope)} ${check.passed ? '通过' : '失败'} · ${ago(check.finished_at)} · ${duration(check.elapsed_seconds)}` : '还没有检查记录';
      return entry(tail(tree.path) + ' · ' + (tree.branch || '分离'), tree.dirty ? chip('有未提交改动', 'warn') : chip('干净'), [text, tree.warning]);
    }), '没有登记的工作树。');
    if (git.warning) root.append(el('p', git.warning, 'quiet'));
  }

  function health() {
    const root = $('health'); root.replaceChildren();
    group(root, '依赖方向问题', (data.dependency_issues || []).map(issue => {
      const where = el('p'); where.append(el('code', `${issue.source}:${issue.line}`)); return entry(issue.message, null, [where], { alert: true });
    }), '依赖方向都符合三种包的规则。');
    group(root, '可能重复的实现', (data.duplicates || []).map(hint => {
      const where = el('p'); hint.locations.forEach((item, index) => { if (index) where.append(document.createTextNode('、')); where.append(el('code', item.source)); });
      return entry(hint.meaning, null, [where], { target: hint.locations[0]?.package });
    }), '没有发现结构相近的重复实现。');
    group(root, '建议拆分', data.nodes.filter(node => node.size?.suggest_split).map(node => entry(node.title, chip(node.size.lines + ' 行'), [`${node.size.steps} 个步骤，${node.size.dependencies} 个依赖。`], { target: node.id })), '所有包的规模都在建议值以内。');
    group(root, '检查不稳定', data.nodes.filter(node => node.flaky).map(node => entry(node.title, chip('⚡', 'warn'), ['同一份代码的检查结果时过时不过，不能当作通过。'], { target: node.id })), '没有发现不稳定的检查。');
  }

  // ===== 指标 =====
  function metrics() {
    const metric = data.metrics || {};
    const history = (metric.history || []).filter(check => typeof check.elapsed_seconds === 'number');
    const rules = metric.rules || {};
    const ruleText = Object.entries(rules).filter(([, value]) => value).map(([key, value]) => (RULE_STATES[key] || key) + ' ' + value).join('，');
    $('metric-summary').textContent = `留存完整检查 ${metric.rounds || 0} 轮，通过率 ${metric.pass_rate == null ? '未知' : Math.round(metric.pass_rate * 100) + '%'}。` + (ruleText ? '规则：' + ruleText + '。' : '');
    chart(history);

    const slow = $('slow-tests'); slow.replaceChildren(); slow.className = 'barlist';
    const tests = metric.slow_tests || [];
    if (!tests.length) slow.append(el('p', '还没有完整检查的测试用时。', 'quiet'));
    const top = Math.max(1, ...tests.map(test => test.seconds));
    tests.forEach(test => {
      const row = el('div', undefined, 'bar-row'), name = test.test.split('::');
      const label = el('span', short(name[name.length - 1], 48), 'label'); label.title = test.test + '（' + test.database + '）';
      const track = el('div', undefined, 'track'), bar = el('span'); bar.style.width = (test.seconds / top * 100) + '%'; track.append(bar);
      row.append(label, el('span', test.seconds.toFixed(1) + ' 秒', 'value'), track); slow.append(row);
    });

    const sizes = $('sizes'); sizes.replaceChildren(); sizes.className = 'barlist';
    const nodes = data.nodes.filter(node => node.size && node.size.lines).sort((a, b) => b.size.lines - a.size.lines).slice(0, 12);
    if (!nodes.length) sizes.append(el('p', '还没有业务代码。', 'quiet'));
    const most = Math.max(1, ...nodes.map(node => Math.max(node.size.lines, node.size.thresholds?.lines || 0)));
    nodes.forEach(node => {
      const row = el('div', undefined, 'bar-row link'), track = el('div', undefined, 'track'), bar = el('span');
      bar.style.width = (node.size.lines / most * 100) + '%'; if (node.size.suggest_split) bar.className = 'over'; track.append(bar);
      if (node.size.thresholds?.lines) { const mark = el('i'); mark.style.left = (node.size.thresholds.lines / most * 100) + '%'; mark.title = '建议上限 ' + node.size.thresholds.lines + ' 行'; track.append(mark); }
      row.append(el('span', node.title + '  ' + node.id, 'label'), el('span', node.size.lines + ' 行', 'value'), track);
      row.addEventListener('click', () => { select(node.id); document.getElementById('map').scrollIntoView({ behavior: 'smooth' }); });
      sizes.append(row);
    });
  }

  function chart(history) {
    const root = $('history'); root.replaceChildren();
    const W = 900, H = 260, L = 52, R = 16, T = 16, B = 34;
    root.setAttribute('viewBox', `0 0 ${W} ${H}`);
    if (!history.length) { const text = svg('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle' }); text.textContent = '还没有完整检查的耗时记录。跑一次 uv run dev check 后这里会出现曲线。'; root.append(text); return; }
    const minutes = history.map(check => check.elapsed_seconds / 60);
    const max = Math.max(1, ...minutes) * 1.12;
    const step = max > 30 ? 10 : max > 10 ? 5 : max > 4 ? 2 : 1;
    const x = index => L + (history.length === 1 ? (W - L - R) / 2 : index * (W - L - R) / (history.length - 1));
    const y = value => T + (1 - value / max) * (H - T - B);
    for (let value = 0; value <= max; value += step) {
      root.append(svg('line', { class: 'grid', x1: L, x2: W - R, y1: y(value), y2: y(value) }));
      const label = svg('text', { x: L - 8, y: y(value) + 4, 'text-anchor': 'end' }); label.textContent = value + ' 分'; root.append(label);
    }
    root.append(svg('line', { class: 'axis', x1: L, x2: W - R, y1: H - B, y2: H - B }));
    const points = minutes.map((value, index) => [x(index), y(value)]);
    root.append(svg('path', { class: 'area', d: `M${points[0][0]},${H - B} ` + points.map(point => 'L' + point.join(',')).join(' ') + ` L${points[points.length - 1][0]},${H - B} Z` }));
    root.append(svg('path', { class: 'trend', d: curve(points.map(([px, py]) => ({ x: px, y: py }))) }));
    const every = Math.max(1, Math.ceil(history.length / 8));
    history.forEach((check, index) => {
      const dot = svg('circle', { cx: points[index][0], cy: points[index][1], r: 4.5, fill: css(check.passed ? '--stable-line' : '--failed-line'), stroke: css('--paper'), 'stroke-width': 2 });
      tip(dot, () => `${new Date(check.finished_at).toLocaleString()}\n${duration(check.elapsed_seconds)}，${check.passed ? '通过' : '失败'}`);
      root.append(dot);
      if (index % every === 0 || index === history.length - 1) {
        const label = svg('text', { x: points[index][0], y: H - 12, 'text-anchor': 'middle' });
        const time = new Date(check.finished_at); label.textContent = Number.isNaN(time.getTime()) ? '' : `${time.getMonth() + 1}/${time.getDate()}`; root.append(label);
      }
    });
  }

  // 统一的悬停提示，替代浏览器自带的慢速 title。
  function tip(target, text) {
    const box = $('tooltip');
    target.addEventListener('mousemove', event => { box.textContent = text(); box.style.whiteSpace = 'pre-line'; box.hidden = false; box.style.left = Math.min(event.clientX + 14, innerWidth - 340) + 'px'; box.style.top = (event.clientY + 16) + 'px'; });
    target.addEventListener('mouseleave', () => { box.hidden = true; });
  }

  $('project-name').textContent = data.name;
  $('generated').textContent = '生成于 ' + new Date(data.generated_at).toLocaleString() + '（' + ago(data.generated_at) + '）';
  $('meaning').textContent = data.meaning || '';
  document.title = data.name + ' · 开发面板';
  overall(); lineFilter(); legend(); interactions(); graph(); overview(); progress(); pending(); work(); health(); metrics();
})();
