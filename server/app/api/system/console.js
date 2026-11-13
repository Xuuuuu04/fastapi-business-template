const notice = document.querySelector('#notice');
const results = document.querySelector('#results');
const filtersForm = document.querySelector('#filters');
const states = {
  overdue_paused: '逾期暂停',
  waiting_members: '等待子任务',
  joining: '正在汇总',
  planned: '子任务等待安排',
  not_started: '未开始',
  succeeded: '已完成',
  queued: '排队中',
  waiting_external: '等待外部服务',
  waiting_retry: '等待重试',
  unknown: '结果待确认',
  version_blocked: '版本暂停',
  cancelled: '已取消',
  ok: '已完成',
  failed: '失败',
  refused: '被拒绝',
  lost: '失去联系',
  running: '执行中',
  skipped: '跳过',
};
const kinds = { compute: '计算', read: '数据访问', save: '保存', call: '模块调用', model: '大模型', remote: '外部接口' };
let current = 'modules';
let pending;
const backStack = [];
const cursorStack = [];

function element(tag, text, className = '') {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function button(text, action, className = '') {
  const node = element('button', text, className);
  node.type = 'button';
  node.addEventListener('click', action);
  return node;
}

function duration(value) {
  if (value === null || value === undefined) return '未知';
  return `${Number(value).toFixed(1)} 毫秒`;
}

function stateBadge(value) {
  return element('span', states[value] || value, `status ${value}`);
}

function timestamp(value) {
  if (value === null || value === undefined || value === '') return '—';
  return new Date(Number(value) * 1000).toLocaleString('zh-CN');
}

function authHeaders() {
  const secret = document.querySelector('#secret').value.trim();
  const kind = document.querySelector('#kind').value;
  return { secret, kind, headers: { [kind]: kind === 'Authorization' ? `Bearer ${secret}` : secret } };
}

function table(parent, headers, rows, numericCols = []) {
  if (!rows.length) {
    parent.append(element('p', '暂无记录', 'empty'));
    return;
  }
  const wrap = element('div', null, 'table-wrap');
  const grid = element('table');
  const head = element('tr');
  headers.forEach((text, index) => head.append(element('th', text, numericCols.includes(index) ? 'num' : '')));
  const thead = element('thead');
  thead.append(head);
  grid.append(thead);
  const body = element('tbody');
  rows.forEach((values) => {
    const row = element('tr');
    values.forEach((value, index) => {
      const cell = element('td', null, numericCols.includes(index) ? 'num' : '');
      cell.append(value instanceof Node ? value : element('span', value ?? '—'));
      row.append(cell);
    });
    body.append(row);
  });
  grid.append(body);
  wrap.append(grid);
  parent.append(wrap);
}

function source(parent, title, text) {
  const detail = element('details');
  detail.append(element('summary', title), element('pre', text));
  parent.append(detail);
}

function sectionHeader(title, showBack = false) {
  const row = element('div', null, 'section-head');
  row.append(element('h2', title));
  if (showBack && backStack.length) {
    row.append(button('← 返回', () => {
      const prev = backStack.pop();
      if (prev) show(prev, { recordHistory: false });
    }));
  }
  results.append(row);
}

function openDetailsSnapshot() {
  return new Set(
    Array.from(results.querySelectorAll('details[open] > summary')).map((node) => node.textContent || '')
  );
}

function restoreDetailsSnapshot(opened) {
  if (!opened.size) return;
  results.querySelectorAll('details').forEach((detail) => {
    const title = detail.querySelector(':scope > summary')?.textContent || '';
    if (opened.has(title)) detail.open = true;
  });
}

function completeness(data) {
  if (!data.records) return;
  const info = data.records;
  results.append(element('p', `${info.note}；执行中 ${info.active} 条，等待保存 ${info.waiting} 条。`, 'muted foot-note'));
}

async function show(path, { recordHistory = true } = {}) {
  const basePath = path.split('?')[0];
  if (recordHistory && current && path !== current) {
    if (backStack[backStack.length - 1] !== current) backStack.push(current);
  }
  if (!basePath.endsWith('/members')) cursorStack.length = 0;
  const previousPath = current;
  current = path;
  filtersForm.hidden = basePath !== 'runs';
  if (pending) pending.abort();
  const { secret, headers } = authHeaders();
  if (!secret) {
    results.replaceChildren();
    notice.textContent = '请先输入凭据。';
    return;
  }
  const opened = previousPath === path ? openDetailsSnapshot() : new Set();
  const controller = new AbortController();
  pending = controller;
  notice.textContent = '正在读取…';
  try {
    const response = await fetch(`/api/system/${path}`, { headers, cache: 'no-store', signal: controller.signal });
    const data = await response.json();
    if (controller.signal.aborted) return;
    results.replaceChildren();
    if (!response.ok) {
      notice.textContent = data.message || `请求失败（${response.status}）`;
      return;
    }
    render(basePath, data);
    completeness(data);
    source(results, '查看原始数据（供 AI 排查）', JSON.stringify(data, null, 2));
    restoreDetailsSnapshot(opened);
    notice.textContent = '查询完成。';
  } catch (error) {
    if (error.name !== 'AbortError') notice.textContent = `无法读取：${error.message}`;
  } finally {
    if (pending === controller) pending = null;
  }
}

function render(path, data) {
  document.querySelectorAll('nav button').forEach((node) => node.classList.toggle('active', node.dataset.path === path));
  if (path === 'pipelines') return pipelines(data);
  if (path.startsWith('pipelines/') && path.endsWith('/members')) return memberDetail(data);
  if (path.startsWith('pipelines/')) return pipelineDetail(data);
  if (path === 'modules') return modules(data);
  if (path.startsWith('flows/')) return flow(data);
  if (path.startsWith('runs/')) return runDetail(data);
  if (path === 'runs') {
    sectionHeader('最近运行');
    table(results, ['业务操作', '状态', '耗时', '发生时间', '结果', '详情'], data.items.map((item) => [
      item.title, stateBadge(item.status), duration(item.elapsed_ms), timestamp(item.started_at), item.summary,
      button('查看步骤', () => show(`runs/${item.id}`)),
    ]), [2]);
  } else if (path === 'stats') {
    sectionHeader(`最近 ${data.hours} 小时的运行统计`);
    table(results, ['操作', '状态', '次数', '平均耗时', '最长耗时'], data.items.map((item) => [
      item.contract, stateBadge(item.status), item.count, duration(item.average_ms), duration(item.max_ms),
    ]), [2, 3, 4]);
  } else if (path === 'runtime') {
    runtime(data);
  } else if (path === 'audit') {
    sectionHeader('操作记录');
    table(results, ['时间', '操作者', '组织', '操作', '状态', '运行编号'], data.items.map((item) => [
      timestamp(item.created_at), item.actor, item.org_id, item.contract, stateBadge(item.status),
      item.run_id ? button(item.run_id, () => show(`runs/${item.run_id}`)) : '无',
    ]));
  }
}

function modules(data) {
  sectionHeader('模块关系');
  results.append(element('p', '点击操作查看步骤；这里显示允许的调用关系。', 'muted'));
  const cards = element('div', null, 'cards');
  const titles = Object.fromEntries(data.modules.map((item) => [item.name, item.title]));
  data.modules.forEach((item) => {
    const card = element('article');
    card.append(element('h3', item.title), element('p', `${item.name} · 版本 ${item.version}`, 'muted'));
    const group = element('div', null, 'btn-group');
    item.operations.forEach((op) => group.append(button(op.title, () => show(`flows/${encodeURIComponent(op.name)}`))));
    card.append(group);
    const links = Object.entries(data.links[item.name] || {});
    if (!links.length) card.append(element('p', '不调用其他模块', 'connection'));
    links.forEach(([target, operations]) =>
      card.append(element('p', `${item.title} → ${titles[target] || target}：${operations.join('、')}`, 'connection'))
    );
    cards.append(card);
  });
  if (!data.modules.length) cards.append(element('p', '当前没有启用业务模块。', 'empty'));
  results.append(cards);
  source(results, '查看自动生成的 Mermaid 关系图', data.graph);
}

function flow(data) {
  sectionHeader(data.title, true);
  results.append(element('p', `${data.module} · ${data.name}`, 'muted'));
  const list = element('ol', null, 'steps');
  data.steps.forEach((part, index) => {
    const row = element('li');
    row.append(element('h3', `${index + 1}. ${part.title} · ${kinds[part.kind] || part.kind}`));
    if (part.condition) row.append(element('p', `执行条件：${part.condition}`));
    row.append(element('p', `读取：${part.reads.join('、') || '无'}；写入：${part.writes.join('、') || '无'}`));
    if (part.calls.length || part.jobs.length) {
      const group = element('div', null, 'btn-group');
      [...part.calls, ...part.jobs].forEach((item) =>
        group.append(button(`查看 ${item.title}`, () => show(`flows/${encodeURIComponent(item.name)}`)))
      );
      row.append(group);
    }
    row.append(element('small', part.source));
    list.append(row);
  });
  results.append(list);
  table(results, ['字段', '含义', '来源'], data.fields.map((item) => [
    item.name, item.meaning, [item.origin, item.step, item.rule].filter(Boolean).join(' · '),
  ]));
  source(results, '查看自动生成的 Mermaid 步骤图', data.graph);
}

function stepDetails(part) {
  const details = element('details');
  details.append(element('summary', '字段、调用和源码位置'));
  details.append(element('p', `读取：${part.reads.join('、') || '无'}；写入：${part.writes.join('、') || '无'}`));
  part.values.forEach((value) => details.append(element('p', value)));
  if (part.outputs_recorded) {
    details.append(element('p', `已写入字段：${Object.keys(part.outputs).length}/${part.writes.length} 个字段`));
  }
  details.append(element('code', `${part.error_place || part.source} · ${part.name}`));
  if (part.condition_source) {
    const condText = part.condition_result === null ? '未知' : part.condition_result ? '执行' : '跳过';
    details.append(element('p', `条件 ${part.condition_name}：${condText}；${duration(part.condition_elapsed_ms)}；${part.condition_source}`));
  }
  if (part.database_count) {
    details.append(element('p', `数据库调用 ${part.database_count} 次，合计 ${duration(part.database_elapsed_ms)}，保留 ${part.database.length} 次细节。`));
    table(details, ['调用', '表或视图', '状态', '耗时', '行数', '函数与位置'], part.database.map((call) => [
      `${call.target}.${call.method}`, call.tables.join('、') || '未知', call.status,
      duration(call.elapsed_ms), call.rows === null ? '未知' : call.rows, `${call.source} · ${call.function}`,
    ]), [3, 4]);
  }
  [...part.models, ...part.remotes].forEach((call) =>
    details.append(element('p', `${call.prompt || call.remote}：${duration(call.elapsed_ms)}${call.error ? `；${call.error}` : ''}`))
  );
  return details;
}

function runDetail(data) {
  sectionHeader('运行详情', true);
  results.append(element('p', data.summary, 'muted'));
  data.runs.forEach((run) => {
    const card = element('article', null, 'run-card');
    card.id = `run-${run.id}`;
    card.append(element('h3', run.title));
    const meta = element('div', null, 'card-meta');
    meta.append(stateBadge(run.status), element('span', `${run.module} · ${duration(run.elapsed_ms)} · ${run.id}`, 'muted'));
    card.append(meta);
    if (run.parent_id) {
      const link = element('a', `上层调用：${run.parent_id}`);
      link.href = `#run-${run.parent_id}`;
      card.append(link);
    }
    if (run.error_message) card.append(element('p', `${run.failed_step || '执行入口'}：${run.error_message}`, 'failed-text'));
    const elapsed = Math.max(0, ...run.steps.filter((item) => item.status !== 'skipped').map((item) => item.elapsed_ms));
    const list = element('ol', null, 'steps');
    run.steps.forEach((part, index) => {
      const slowest = elapsed > 0 && part.elapsed_ms === elapsed;
      const row = element('li', null, `${part.status}${slowest ? ' slowest' : ''}`);
      row.append(element('h3', `${index + 1}. ${part.title}`));
      const top = element('div', null, 'step-top');
      top.append(stateBadge(part.status), element('span', `${duration(part.elapsed_ms)}${slowest ? ' · 本次记录耗时最长步骤' : ''}`, 'muted'));
      row.append(top);
      if (part.error_message) row.append(element('p', part.error_message, 'failed-text'));
      part.notes.forEach((note) => row.append(element('p', note)));
      part.children.forEach((id) => {
        const link = element('a', `查看下层调用 ${id}`);
        link.href = `#run-${id}`;
        row.append(link);
      });
      row.append(stepDetails(part));
      list.append(row);
    });
    if (!run.steps.length) card.append(element('p', '没有执行任何步骤。', 'muted'));
    const remaining = run.planned.filter((name) => !run.steps.some((part) => part.name === name));
    if (remaining.length) card.append(element('p', `尚未执行：${remaining.join('、')}`, 'muted foot-note'));
    card.append(list);
    results.append(card);
  });
  source(results, '查看自动生成的 Mermaid 实际执行图', data.graph);
}

function runtime(data) {
  sectionHeader('进程状态');
  table(results, ['项目', '当前值'], [
    ['环境', data.env],
    ['代码版本', data.code_version],
    ['内存', `${data.memory_mb} MB`],
    ['正在处理的请求', data.inflight_requests],
    ['线程数', data.threads],
    ['数据库连接池', data.database_pool],
    ['后台任务', typeof data.jobs === 'string' ? data.jobs : Object.entries(data.jobs).map(([k, v]) => `${k}：${v}`).join('；') || '暂无任务'],
    ['外部服务', Object.entries(data.breakers).map(([k, v]) => `${k}：${v}`).join('；') || '未使用'],
  ]);
}

function pipelines(data) {
  sectionHeader('业务流程');
  table(results, ['流程', '组织 / 周期', '当前阶段', '状态', '原因', '详情'], data.items.map((item) => [
    item.pipeline, `${item.org_id} / ${item.cycle_key}`, item.current_stage || '未开始', stateBadge(item.state), item.reason,
    button('查看阶段', () => show(`pipelines/${item.id}`)),
  ]));
}

function formatStateCounts(counts) {
  return Object.entries(counts || {}).map(([key, count]) => `${states[key] || key} ${count}`).join('，') || '无';
}

function pipelineDetail(data) {
  sectionHeader(data.pipeline, true);
  const meta = element('div', null, 'card-meta');
  meta.append(stateBadge(data.state), element('span', data.reason || '', 'muted'));
  results.append(meta);
  if (data.overdue) {
    results.append(element('p', `已逾期；最晚完成 ${timestamp(data.complete_by)}；通知状态 ${data.notification_state || '未知'}`, 'warning'));
  }
  table(results, ['阶段', '状态', '耗时', '实际版本', '尝试 / 轮询', '运行记录'], data.stages.map((item) => [
    item.name, stateBadge(item.state), duration(item.elapsed_ms), item.module_version || '未知',
    `${item.attempt} / ${item.poll_count}`, item.run_id ? button('查看运行', () => show(`runs/${item.run_id}`)) : '未知',
  ]), [2]);
  results.append(element('p', data.source_fixed ? '本次流程使用的数据来源已固定' : '本次流程使用的数据来源尚未固定', 'muted foot-note'));
  data.stages.filter((item) => item.members).forEach((item) => {
    const row = element('div', null, 'pager');
    row.append(
      element('span', `${item.name}：${formatStateCounts(item.members.states)}；计入汇总 ${item.members.accepted}`),
      button('查看子任务', () => show(`pipelines/${data.id}/members?stage=${encodeURIComponent(item.name)}`))
    );
    results.append(row);
  });
  source(results, '查看整条流程运行图', data.graph);
  if (['failed', 'version_blocked', 'unknown', 'overdue_paused'].includes(data.state)) {
    const box = element('div', null, 'recovery-box');
    const schema = element('input');
    schema.type = 'checkbox';
    const unknown = element('input');
    unknown.type = 'checkbox';
    const schemaLabel = element('label', null, 'check-label');
    schemaLabel.append(schema, element('span', '已审查并接受当前格式'));
    const unknownLabel = element('label', null, 'check-label');
    unknownLabel.append(unknown, element('span', '已向外部服务确认原请求没有执行，可以重新执行'));
    box.append(schemaLabel, unknownLabel, button('从当前阶段恢复', async () => {
      if (!confirm('确认只从当前失败阶段重新执行？')) return;
      const { headers } = authHeaders();
      const response = await fetch(`/api/system/pipelines/${data.id}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ accept_schema: schema.checked, confirm_unknown: unknown.checked }),
      });
      const result = await response.json();
      if (response.ok) await show(`pipelines/${data.id}`, { recordHistory: false });
      else notice.textContent = result.message || result.detail || '恢复失败';
    }));
    results.append(box);
  }
}

function memberDetail(data) {
  sectionHeader('并行子任务', true);
  table(results, ['子任务', '当前子阶段', '状态', '计入汇总', '耗时', '版本', '运行'], data.items.map((item) => [
    item.key, item.phase_name, stateBadge(item.state), item.accepted ? '是' : '否', duration(item.elapsed_ms),
    item.module_version || '未知', item.run_id ? button('查看运行', () => show(`runs/${item.run_id}`)) : '未知',
  ]), [4]);
  const pager = element('div', null, 'pager');
  if (cursorStack.length) {
    pager.append(button('上一页', () => {
      const prevUrl = cursorStack.pop();
      if (prevUrl) show(prevUrl, { recordHistory: false });
    }));
  }
  if (data.next_after) {
    pager.append(button('下一页', () => {
      cursorStack.push(current);
      const next = new URLSearchParams(current.split('?')[1] || '');
      next.set('after', data.next_after);
      show(`${current.split('?')[0]}?${next}`, { recordHistory: false });
    }));
  }
  if (pager.childElementCount) results.append(pager);
}

document.querySelector('#access').addEventListener('submit', (event) => {
  event.preventDefault();
  show(current, { recordHistory: false });
});
document.querySelector('#report').addEventListener('submit', (event) => {
  event.preventDefault();
  const run = document.querySelector('#run').value.trim();
  if (!/^[0-9a-f]{8,64}$/.test(run)) {
    notice.textContent = '运行编号只包含数字和小写字母 a 到 f。';
    return;
  }
  show(`runs/${run}`);
});
filtersForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const query = new URLSearchParams({
    module: document.querySelector('#module').value.trim(),
    status: document.querySelector('#status').value,
  });
  show(`runs?${query}`, { recordHistory: false });
});
document.querySelectorAll('button[data-path]').forEach((node) => {
  node.addEventListener('click', () => {
    backStack.length = 0;
    show(node.dataset.path, { recordHistory: false });
  });
});
document.querySelector('#refresh').addEventListener('click', () => show(current, { recordHistory: false }));
setInterval(() => {
  const auto = document.querySelector('#auto');
  const editing = results.querySelector('input[type="checkbox"]:checked');
  if (auto.checked && !document.hidden && !pending && !editing) show(current, { recordHistory: false });
}, 3000);
