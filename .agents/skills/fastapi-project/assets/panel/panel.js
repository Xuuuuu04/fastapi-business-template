/* 离线面板只从内嵌数据读取，所有业务文字使用textContent，不执行备注或外部请求。 */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('panel-data').textContent);
  const states = {
    planned:['计划','#e8ebe5'], skeleton:['骨架','#fff'], developing:['开发中','#f4e4a4'],
    unknown:['缺少证据','#e0e5df'], stale:['证据过期','#d8ddea'], checked:['待验证稳定性','#d6e5db'],
    stable:['稳定通过','#8bb99b'], failed:['当前检查失败','#ecb5aa']
  };
  const $ = id => document.getElementById(id);
  const el = (tag,text,klass) => { const element=document.createElement(tag); if(text!==undefined)element.textContent=text; if(klass)element.className=klass; return element; };
  const svgEl = (tag,attrs) => { const element=document.createElementNS('http://www.w3.org/2000/svg',tag); for(const [name,value]of Object.entries(attrs||{}))element.setAttribute(name,String(value)); return element; };
  const pretty = value => value===null||value===undefined?'未知':typeof value==='object'?JSON.stringify(value):String(value);
  function table(id,headers,rows) {
    const root=$(id);root.replaceChildren();
    if(!rows.length){root.append(el('p','暂无资料。','muted'));return;}
    const wrap=el('div',undefined,'table-wrap'), grid=el('table'),head=el('tr');
    headers.forEach(header=>head.append(el('th',header)));const thead=el('thead');thead.append(head);grid.append(thead);
    const body=el('tbody');rows.forEach(row=>{const line=el('tr');row.forEach(value=>line.append(el('td',pretty(value))));body.append(line);});
    grid.append(body);wrap.append(grid);root.append(wrap);
  }
  function detail(node) {
    const root=$('detail');root.replaceChildren(el('h2',node.title),el('code',node.id));
    root.append(el('p',states[node.state][0]+' · '+node.reason),el('p','业务线：'+node.line+'；类别：'+node.kind));
    if(node.flaky)root.append(el('p','同一源码出现成功与失败，检查不稳定。','warning'));
    if(node.pending_confirmation)root.append(el('p','有高风险规则需要明确确认。','warning'));
    if(node.size.suggest_split)root.append(el('p','规模超过整理建议值，请评估拆包。','warning'));
    root.append(el('h3','实现与步骤'));
    if(!node.operations.length)root.append(el('p','尚无公开操作实现。'));
    node.operations.forEach(operation=>{
      root.append(el('strong',operation.title),el('p',operation.name+' · '+operation.implementation));
      operation.steps.forEach(step=>root.append(el('code',step.name+' · '+step.source+(step.simulated?'（模拟）':''))));
    });
    root.append(el('h3','规则确认'));
    if(!node.rules.length)root.append(el('p','尚无规则账本记录。'));
    node.rules.forEach(rule=>root.append(el('p',rule.id+' · '+rule.state+' · '+rule.risk)));
    root.append(el('h3','检查原件'));
    if(!node.checks.length)root.append(el('p','没有正式检查记录。'));
    node.checks.forEach(check=>root.append(el('code',check)));
    (node.recent_records||[]).forEach(record=>{
      root.append(el('p',record.finished_at+' · '+(record.current_module?'当前包源码':'过期包源码')+' · '+pretty(record.scope)));
      record.suites.forEach(suite=>root.append(el('p',suite.database+'：'+pretty(suite.counts)+'；测试累计 '+suite.test_seconds+' 秒')));
      root.append(el('p','整轮耗时 '+pretty(record.elapsed_seconds)+' 秒；'+(record.passed?'检查通过':'检查失败')));
    });
    if((node.duplicates||[]).length)root.append(el('h3','重复实现提示'));
    (node.duplicates||[]).forEach(hint=>root.append(el('p',hint.locations.map(item=>item.source).join('、')+'；'+hint.meaning)));
    root.append(el('h3','源码规模'),el('p',node.size.lines+' 行；'+node.size.steps+' 步骤；'+node.size.dependencies+' 依赖'));
    if(node.note)root.append(el('h3','备注（不参与检查状态）'),el('p',node.note));
  }
  function graph() {
    const line=$('line-filter').value, query=$('search').value.trim().toLowerCase();
    const selected=data.nodes.filter(node=>(!line||node.line===line)&&(!query||(node.id+' '+node.title).toLowerCase().includes(query)));
    const root=$('graph');root.replaceChildren();$('empty').hidden=selected.length>0;root.style.display=selected.length?'block':'none';
    if(!selected.length)return;
    const names=new Set(selected.map(node=>node.id));
    const layout=new dagre.graphlib.Graph({multigraph:true}).setGraph({rankdir:'LR',nodesep:32,ranksep:70,marginx:25,marginy:25}).setDefaultEdgeLabel(()=>({}));
    selected.forEach(node=>layout.setNode(node.id,{width:190,height:72}));
    const edges=data.edges.filter(edge=>names.has(edge.source)&&names.has(edge.target));
    edges.forEach((edge,index)=>layout.setEdge(edge.source,edge.target,{},String(index)));dagre.layout(layout);
    root.setAttribute('viewBox','0 0 '+Math.max(550,layout.graph().width)+' '+Math.max(250,layout.graph().height));
    root.style.width=Math.max(550,layout.graph().width)+'px';root.style.height=Math.max(480,layout.graph().height)+'px';
    const defs=svgEl('defs'),marker=svgEl('marker',{id:'arrow',viewBox:'0 0 10 10',refX:8,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
    marker.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#809279'}));defs.append(marker);root.append(defs);
    edges.forEach((edge,index)=>{
      const points=layout.edge({v:edge.source,w:edge.target,name:String(index)}).points;
      const path=svgEl('path',{d:points.map((point,i)=>(i?'L':'M')+point.x+','+point.y).join(' '),'class':'edge','stroke-width':Math.min(5,1+edge.count*.5),'marker-end':'url(#arrow)'});
      if(edge.kind==='planned')path.setAttribute('stroke-dasharray','6 5');
      if(edge.kind==='exception')path.style.stroke='#aa78b0';
      if(edge.kind==='library')path.style.stroke='#7396b8';
      if(edge.kind==='invalid')path.style.stroke='#c14736';
      const title=svgEl('title');title.textContent=edge.source+' → '+edge.target+'；'+edge.kind+'；'+edge.count+' 操作';path.append(title);root.append(path);
    });
    selected.forEach(node=>{
      const position=layout.node(node.id),group=svgEl('g',{'class':'node',transform:'translate('+(position.x-95)+','+(position.y-36)+')',tabindex:0,role:'button','aria-label':node.title+'，'+states[node.state][0]});
      const box=svgEl('rect',{width:190,height:72,rx:7,fill:states[node.state][1],stroke:node.size.suggest_split?'#cb8f4f':'#9aaf91','stroke-width':node.size.suggest_split?3:1});
      if(node.state==='planned')box.setAttribute('stroke-dasharray','6 4');group.append(box);
      const title=svgEl('text',{x:12,y:26,'class':'title'});title.textContent=node.title.length>13?node.title.slice(0,12)+'…':node.title;group.append(title);
      const name=svgEl('text',{x:12,y:47,'class':'name'});name.textContent=node.id.length>25?node.id.slice(0,24)+'…':node.id;group.append(name);
      const state=svgEl('text',{x:12,y:63,'class':'name'});state.textContent=states[node.state][0]+(node.flaky?' · ⚡':'');group.append(state);
      if(node.pending_confirmation)group.append(svgEl('circle',{cx:176,cy:12,r:5,fill:'#9564b5'}));
      group.addEventListener('click',()=>detail(node));group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();detail(node);}});root.append(group);
    });
  }
  function progress() {
    table('line-progress',['业务线','计划操作','模拟骨架','真实实现','稳定通过操作','已确认 / 全部规则'],data.lines.map(line=>{
      const nodes=data.nodes.filter(node=>line.packages.includes(node.id)),operations=nodes.flatMap(node=>node.operations),rules=nodes.flatMap(node=>node.rules);
      return [line.name,nodes.reduce((sum,node)=>sum+node.planned_operations.length,0),operations.filter(operation=>operation.implementation==='skeleton').length,operations.filter(operation=>operation.implementation==='real').length,nodes.filter(node=>node.state==='stable').reduce((sum,node)=>sum+node.operations.length,0),rules.filter(rule=>rule.state==='confirmed').length+' / '+rules.length];
    }));
  }
  function work() {
    table('tasks',['包','任务','当前状态','记录状态','原因'],data.tasks.map(task=>[task.package,task.id,task.state,task.recorded_state,task.reasons]));
    table('branches',['分支','变化包','变化文件','框架改动'],data.git.branches.map(branch=>[branch.name,branch.packages,branch.changed_files,branch.framework_changed?'有':'无']));
    table('worktrees',['工作树 / 分支','本地修改','独立历史检查','适用范围说明'],data.git.worktrees.map(tree=>[tree.path+' / '+tree.branch,tree.dirty?'有':'无',tree.latest_check,tree.warning||tree.meaning]));
    const overlaps=$('overlaps');data.git.overlaps.forEach(overlap=>overlaps.append(el('p',overlap.package+' 同时变化于 '+overlap.branches.join('、')+'，整合时需要核对。','warning')));
    if(data.git.warning)overlaps.append(el('p',data.git.warning,'warning'));
  }
  function pending() {
    const root=$('pending');
    const sections=[['待确认规则',data.attention.rules],['契约修改请求',data.attention.contract_requests],['收工审查单',data.attention.reviews]];
    sections.forEach(([title,items])=>{root.append(el('h3',title));if(!items.length)root.append(el('p','暂无资料。'));items.forEach(item=>root.append(el('div',pretty(item),'list-row')));});
    table('dependency-issues',['源码','行号','规则','说明'],(data.dependency_issues||[]).map(issue=>[issue.source,issue.line,issue.rule,issue.message]));
    table('duplicates',['位置','提示'],(data.duplicates||[]).map(hint=>[hint.locations.map(item=>item.source),hint.meaning]));
  }
  function metrics() {
    const metrics=data.metrics;
    $('metric-summary').append(el('p','留存完整检查 '+metrics.rounds+' 轮；通过率 '+(metrics.pass_rate===null?'未知':(metrics.pass_rate*100).toFixed(1)+'%')+'。规则分布 '+pretty(metrics.rules)));
    table('slow-tests',['测试','数据库','秒数','结果'],metrics.slow_tests.map(test=>[test.test,test.database,test.seconds,test.outcome]));
    table('sizes',['包','行数','步骤','依赖','整理建议'],data.nodes.map(node=>[node.id,node.size.lines,node.size.steps,node.size.dependencies,node.size.suggest_split?'评估拆包':'未超过建议值']));
    const svg=$('history'),history=metrics.history.filter(check=>typeof check.elapsed_seconds==='number');svg.setAttribute('viewBox','0 0 1000 160');
    if(!history.length){const text=svgEl('text',{x:24,y:80});text.textContent='还没有完整检查耗时记录。';svg.append(text);return;}
    const max=Math.max(1,...history.map(check=>check.elapsed_seconds));
    const points=history.map((check,index)=>({x:35+index*930/Math.max(1,history.length-1),y:135-check.elapsed_seconds/max*110,check}));
    svg.append(svgEl('polyline',{points:points.map(point=>point.x+','+point.y).join(' '),fill:'none',stroke:'#8da989','stroke-width':2}));
    points.forEach(point=>{const circle=svgEl('circle',{cx:point.x,cy:point.y,r:4,fill:point.check.passed?'#417b58':'#b66550'}),title=svgEl('title');title.textContent=point.check.finished_at+'；'+point.check.elapsed_seconds+' 秒；'+(point.check.passed?'通过':'失败');circle.append(title);svg.append(circle);});
    const label=svgEl('text',{x:15,y:15,fill:'#637466','font-size':12});label.textContent='完整检查耗时（最近 '+history.length+' 轮，最高 '+max.toFixed(1)+' 秒）';svg.append(label);
  }
  $('project-name').textContent=data.name;$('generated').textContent='生成于 '+new Date(data.generated_at).toLocaleString();$('meaning').textContent=data.meaning;document.title=data.name+' · 开发面板';
  Object.entries(states).forEach(([state,[label,color]])=>{const item=el('span',undefined,'legend-item'),swatch=el('span',undefined,'swatch');swatch.style.background=color;item.append(swatch,el('span',label));$('legend').append(item);});
  [...new Set(data.nodes.map(node=>node.line))].forEach(line=>{const option=el('option',line);option.value=line;$('line-filter').append(option);});
  $('line-filter').addEventListener('change',graph);$('search').addEventListener('input',graph);$('fit').addEventListener('click',()=>{graph();$('graph').style.width='100%';$('graph').style.height='100%';});
  graph();progress();work();pending();metrics();
})();
