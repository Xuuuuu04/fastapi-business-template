// 页面调用系统查询和流程恢复接口；所有业务文字按纯文本显示，不执行记录中的内容。
const notice = document.querySelector('#notice');
const results = document.querySelector('#results');
const states = {not_started:'未开始',succeeded:'已完成',queued:'排队中',waiting_external:'等待上游',waiting_retry:'等待重试',unknown:'结果待确认',version_blocked:'版本暂停',cancelled:'已取消',ok:'已完成',failed:'失败',refused:'被拒绝',lost:'失去联系',running:'执行中',skipped:'跳过'};
const kinds = {compute:'计算',read:'数据访问',save:'保存',call:'模块调用',model:'大模型',remote:'外部接口'};
let current = 'modules';
let pending;

function element(tag, text, className = '') {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  node.className = className;
  return node;
}
function button(text, action) {
  const node = element('button', text);
  node.type = 'button';
  node.addEventListener('click', action);
  return node;
}
function duration(value) { if (value === null || value === undefined) return "未知"; return `${Number(value).toFixed(1)} 毫秒`; }
function state(value) { return element('span', states[value] || value, `status ${value}`); }
function timestamp(value) { return new Date(value * 1000).toLocaleString('zh-CN'); }
function table(parent, headers, rows) {
  if (!rows.length) { parent.append(element('p', '暂无记录', 'empty')); return; }
  const wrap = element('div', null, 'table-wrap');
  const grid = element('table');
  const head = element('tr');
  headers.forEach(text => head.append(element('th', text)));
  const thead = element('thead'); thead.append(head); grid.append(thead);
  const body = element('tbody');
  rows.forEach(values => {
    const row = element('tr');
    values.forEach(value => {
      const cell = element('td');
      cell.append(value instanceof Node ? value : element('span', value ?? '—'));
      row.append(cell);
    });
    body.append(row);
  });
  grid.append(body); wrap.append(grid); parent.append(wrap);
}
function source(parent, title, text) {
  const detail = element('details');
  detail.append(element('summary', title), element('pre', text));
  parent.append(detail);
}
function completeness(data) {
  if (!data.records) return;
  const info = data.records;
  results.append(element('p', `${info.note}；执行中 ${info.active} 条，等待保存 ${info.waiting} 条。`, 'muted'));
}
// 切换查询时取消旧请求，防止慢请求覆盖已经切换的页面。
async function show(path) {
  current = path;
  if (pending) pending.abort();
  const secret = document.querySelector('#secret').value.trim();
  if (!secret) { results.replaceChildren(); notice.textContent = '请先输入凭据。'; return; }
  const controller = new AbortController(); pending = controller;
  const kind = document.querySelector('#kind').value;
  const headers = {[kind]:kind === 'Authorization' ? `Bearer ${secret}` : secret};
  notice.textContent = '正在读取…';
  try {
    const response = await fetch(`/api/system/${path}`, {headers,cache:'no-store',signal:controller.signal});
    const data = await response.json();
    if (controller.signal.aborted) return;
    results.replaceChildren();
    if (!response.ok) { notice.textContent = data.message || `请求失败（${response.status}）`; return; }
    render(path.split('?')[0], data);
    completeness(data);
    source(results, '查看原始数据（供 AI 排查）', JSON.stringify(data, null, 2));
    notice.textContent = '查询完成。';
  } catch (error) {
    if (error.name !== 'AbortError') notice.textContent = `无法读取：${error.message}`;
  } finally { if (pending === controller) pending = null; }
}
function render(path, data) {
  document.querySelectorAll('nav button').forEach(node => node.classList.toggle('active', node.dataset.path === path));
  if (path === 'pipelines') return pipelines(data);
  if (path.startsWith('pipelines/')) return pipelineDetail(data);
  if (path === 'modules') return modules(data);
  if (path.startsWith('flows/')) return flow(data);
  if (path.startsWith('runs/')) return runDetail(data);
  if (path === 'runs') {
    results.append(element('h2', '最近运行'));
    table(results, ['业务操作','状态','耗时','发生时间','结果','详情'], data.items.map(item => [
      item.title,state(item.status),duration(item.elapsed_ms),timestamp(item.started_at),item.summary,
      button('查看步骤', () => show(`runs/${item.id}`))]));
  } else if (path === 'stats') {
    results.append(element('h2', `最近 ${data.hours} 小时的运行统计`));
    table(results,['操作','状态','次数','平均耗时','最长耗时'],data.items.map(item => [
      item.contract,state(item.status),item.count,duration(item.average_ms),duration(item.max_ms)]));
  } else if (path === 'runtime') runtime(data);
  else if (path === 'audit') {
    results.append(element('h2','操作记录'));
    table(results,['时间','操作者','组织','操作','状态','运行编号'],data.items.map(item => [
      timestamp(item.created_at),item.actor,item.org_id,item.contract,state(item.status),
      item.run_id ? button(item.run_id, () => show(`runs/${item.run_id}`)) : '无']));
  }
}
// 模块和调用关系直接来自登记清单；操作按钮打开该操作的步骤图。
function modules(data) {
  results.append(element('h2','模块关系'),element('p','点击操作查看步骤。这里显示允许的调用关系，实际执行情况在“最近运行”中查看。','muted'));
  const cards = element('div', null, 'cards');
  const titles = Object.fromEntries(data.modules.map(item => [item.name,item.title]));
  data.modules.forEach(item => {
    const card = element('article');
    card.append(element('h3', item.title),element('p',`${item.name} · 版本 ${item.version}`,'muted'));
    item.operations.forEach(op => card.append(button(op.title, () => show(`flows/${encodeURIComponent(op.name)}`))));
    const links = Object.entries(data.links[item.name] || {});
    if (!links.length) card.append(element('p','不调用其他模块','muted'));
    links.forEach(([target, operations]) => card.append(element('p',`${item.title} → ${titles[target]}：${operations.join('、')}`,'connection')));
    cards.append(card);
  });
  if (!data.modules.length) cards.append(element('p','当前没有启用业务模块。','empty'));
  results.append(cards);
  source(results,'查看自动生成的 Mermaid 关系图',data.graph);
}
function flow(data) {
  results.append(element('h2',data.title),element('p',`${data.module} · ${data.name}`,'muted'));
  const list = element('ol',null,'steps');
  data.steps.forEach((part,index) => {
    const row = element('li');
    row.append(element('h3',`${index+1}. ${part.title} · ${kinds[part.kind]}`));
    if (part.condition) row.append(element('p',`执行条件：${part.condition}`));
    row.append(element('p',`读取：${part.reads.join('、') || '无'}；写入：${part.writes.join('、') || '无'}`));
    [...part.calls,...part.jobs].forEach(item => row.append(button(`查看 ${item.title}`, () => show(`flows/${encodeURIComponent(item.name)}`))));
    row.append(element('small',`${part.rule || '无规则编号'} · ${part.source}`));
    list.append(row);
  });
  results.append(list);
  table(results,['字段','含义','来源'],data.fields.map(item => [item.name,item.meaning,[item.origin,item.step,item.rule].filter(Boolean).join(' · ')]));
  source(results,'查看自动生成的 Mermaid 步骤图',data.graph);
}
// 按实际调用分组显示步骤；耗时最长仅表示本次用时，不能据此判定所有请求的性能原因。
function runDetail(data) {
  results.append(element('h2','运行详情'),element('p',data.summary));
  data.runs.forEach(run => {
    const card = element('article'); card.id = `run-${run.id}`;
    card.append(element('h3',run.title),state(run.status),element('p',`${run.module} · ${duration(run.elapsed_ms)} · ${run.id}`,'muted'));
    if (run.parent_id) {
      const link = element('a',`上层调用：${run.parent_id}`); link.href = `#run-${run.parent_id}`; card.append(link);
    }
    if (run.error_message) card.append(element('p',`${run.failed_step || '执行入口'}：${run.error_message}`,'failed'));
    const elapsed = Math.max(0,...run.steps.filter(item => item.status !== 'skipped').map(item => item.elapsed_ms));
    const list = element('ol',null,'steps');
    run.steps.forEach((part,index) => {
      const slowest = elapsed > 0 && part.elapsed_ms === elapsed;
      const row = element('li',null,`${part.status}${slowest ? ' slowest' : ''}`);
      row.append(element('h3',`${index+1}. ${part.title}`),state(part.status),element('p',`${duration(part.elapsed_ms)}${slowest ? ' · 本次已记录步骤中用时最长' : ''}`));
      if (part.error_message) row.append(element('p',part.error_message,'failed'));
      part.notes.forEach(note => row.append(element('p',note)));
      const details = element('details'); details.append(element('summary','字段、调用和源码位置'));
      details.append(element('p',`读取：${part.reads.join('、') || '无'}；写入：${part.writes.join('、') || '无'}`));
      part.values.forEach(value => details.append(element('p',value)));
      if (part.outputs_recorded) details.append(element('p',`实际产出：${Object.keys(part.outputs).length}/${part.writes.length} 个字段`));
      details.append(element('code',`${part.error_place || part.source} · ${part.name}`));
      if (part.condition_source) details.append(element('p',`条件 ${part.condition_name}：${part.condition_result === null ? '未知' : part.condition_result ? '执行' : '跳过'}；${duration(part.condition_elapsed_ms)}；${part.condition_source}`));
      if (part.database_count) {
        details.append(element('p',`数据库调用 ${part.database_count} 次，合计 ${duration(part.database_elapsed_ms)}，保留 ${part.database.length} 次细节。`));
        table(details,['调用','表或视图','状态','耗时','行数','函数与位置'],part.database.map(call => [
          `${call.target}.${call.method}`,call.tables.join('、') || '未知',call.status,duration(call.elapsed_ms),call.rows === null ? '未知' : call.rows,`${call.source} · ${call.function}`]));
      }
      [...part.models,...part.remotes].forEach(call => details.append(element('p',`${call.prompt || call.remote}：${duration(call.elapsed_ms)}${call.error ? `；${call.error}` : ''}`)));
      part.children.forEach(id => { const link = element('a',`查看下层调用 ${id}`); link.href = `#run-${id}`; row.append(link); });
      row.append(details); list.append(row);
    });
    if (!run.steps.length) card.append(element('p','没有执行任何步骤。','muted'));
    const remaining = run.planned.filter(name => !run.steps.some(part => part.name === name));
    if (remaining.length) card.append(element('p',`尚未执行：${remaining.join('、')}`,'muted'));
    card.append(list); results.append(card);
  });
  source(results,'查看自动生成的 Mermaid 实际执行图',data.graph);
}
function runtime(data) {
  results.append(element('h2','进程状态'));
  table(results,['项目','当前值'],[
    ['环境',data.env],['代码版本',data.code_version],['内存',`${data.memory_mb} MB`],
    ['正在处理的请求',data.inflight_requests],['线程数',data.threads],['数据库连接池',data.database_pool],
    ['后台任务',typeof data.jobs === 'string' ? data.jobs : Object.entries(data.jobs).map(([key,value]) => `${key}：${value}`).join('；') || '暂无任务'],
    ['外部服务',Object.entries(data.breakers).map(([key,value]) => `${key}：${value}`).join('；') || '未使用']]);
}
document.querySelector('#access').addEventListener('submit', event => event.preventDefault());
document.querySelector('#report').addEventListener('submit', event => {
  event.preventDefault();
  const run = document.querySelector('#run').value.trim();
  if (!/^[0-9a-f]{8,64}$/.test(run)) { notice.textContent = '运行编号只包含数字和小写字母 a 到 f。'; return; }
  show(`runs/${run}`);
});
document.querySelector('#filters').addEventListener('submit', event => {
  event.preventDefault();
  const query = new URLSearchParams({module:document.querySelector('#module').value.trim(),status:document.querySelector('#status').value});
  show(`runs?${query}`);
});
document.querySelectorAll('button[data-path]').forEach(node => node.addEventListener('click', () => show(node.dataset.path)));
document.querySelector('#refresh').addEventListener('click', () => show(current));
setInterval(() => {
  if (document.querySelector('#auto').checked && !document.hidden && !pending) show(current);
},3000);

// 摘要进入阶段详情，恢复需明确确认当前版本和未知外部结果。
function pipelines(data) {
  results.append(element('h2','业务流程'));
  table(results,['流程','组织 / 周期','当前阶段','状态','原因','详情'],data.items.map(item => [
    item.pipeline,`${item.org_id} / ${item.cycle_key}`,item.current_stage || '未开始',state(item.state),item.reason,
    button('查看阶段',() => show(`pipelines/${item.id}`))]));
}
function pipelineDetail(data) {
  results.append(element('h2',data.pipeline),state(data.state),element('p',data.reason));
  table(results,['阶段','状态','耗时','实际版本','尝试 / 轮询','运行记录'],data.stages.map(item => [
    item.name,state(item.state),duration(item.elapsed_ms),item.module_version || '未知',
    `${item.attempt} / ${item.poll_count}`,item.run_id ? button('查看运行',() => show(`runs/${item.run_id}`)) : '未知']));
  source(results,'查看整条流程运行图',data.graph);
  if (['failed','version_blocked','unknown'].includes(data.state)) {
    const schema = element('input'); schema.type = 'checkbox';
    const unknown = element('input'); unknown.type = 'checkbox';
    const schemaLabel = element('label'); schemaLabel.append(schema,element('span','已审查并接受当前格式'));
    const unknownLabel = element('label'); unknownLabel.append(unknown,element('span','已确认外部未产生效果，可重新执行'));
    results.append(schemaLabel,unknownLabel,button('从当前阶段恢复',async () => {
      if (!confirm('确认只从当前失败阶段重新执行？')) return;
      const secret = document.querySelector('#secret').value.trim();
      const kind = document.querySelector('#kind').value;
      const response = await fetch(`/api/system/pipelines/${data.id}/resume`,{method:'POST',
        headers:{'Content-Type':'application/json',[kind]:kind === 'Authorization' ? `Bearer ${secret}` : secret},
        body:JSON.stringify({accept_schema:schema.checked,confirm_unknown:unknown.checked})});
      const result = await response.json();
      if (response.ok) await show(`pipelines/${data.id}`);
      else notice.textContent = result.message || result.detail || '恢复失败';
    }));
  }
}
