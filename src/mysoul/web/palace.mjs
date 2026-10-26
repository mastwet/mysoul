// Operator-only native browser. Text from the palace is always rendered literally.
export function createPalaceBrowser({document,api}) {
  const $=id=>document.getElementById(id);
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const button=(text,action,cls='secondary small')=>{const b=el('button',text,cls);b.type='button';b.addEventListener('click',action);return b;};
  let overview=null,page=null,selected='',pageRequest=0,detailRequest=0,overviewRequest=0;
  let opened=false,refreshing=false,listing=false,retryQuery=null,retryDetail='';
  const date=value=>value?new Date(value).toLocaleString('zh-CN'):'未记录';
  const wingLabel=id=>overview?.wings?.find(w=>w.id===id)?.label||id||'全部 Wings';
  const roomLabel=id=>id.startsWith('evidence-')?`证据房间 · ${id.slice(9,17)}`:id;

  function fields(target,pairs) {
    target.replaceChildren();
    for(const [label,value] of pairs){target.append(el('dt',label),el('dd',String(value??'未记录')));}
  }
  function controls(){
    $('palace-refresh').disabled=refreshing;
    $('palace-wing').disabled=refreshing;
    $('palace-prev').disabled=refreshing||listing||!page||page.offset===0;
    $('palace-next').disabled=refreshing||listing||!page||page.offset+page.limit>=page.total;
    $('palace-list').setAttribute('aria-busy',String(listing));
  }
  function rooms(){
    const wing=$('palace-wing').value,filter=$('palace-room-filter').value.trim().toLocaleLowerCase();
    const source=overview?.wings?.find(w=>w.id===wing)?.rooms||[];
    const root=$('palace-rooms');root.replaceChildren();
    if(!wing){$('palace-room-count').textContent='';root.append(el('p','选择 Wing 后浏览其中的房间。','field-note'));return;}
    const all=button('全部房间',()=>loadPage({wing,room:'',offset:0}),'palace-room');
    all.disabled=refreshing;all.setAttribute('aria-pressed',String(page?.wing===wing&&!page?.room));root.append(all);
    const matches=source.filter(r=>r.id.toLocaleLowerCase().includes(filter));
    for(const r of matches){
      const b=button('',()=>loadPage({wing,room:r.id,offset:0}),'palace-room');
      b.dataset.room=r.id;b.title=r.id;b.disabled=refreshing;
      b.setAttribute('aria-pressed',String(page?.wing===wing&&page?.room===r.id));
      b.append(el('span',roomLabel(r.id)),el('small',`${r.chunks.toLocaleString()} 分块`));root.append(b);
    }
    if(!matches.length)root.append(el('p',filter?'没有匹配的房间。':'此 Wing 没有房间。','field-note'));
    $('palace-room-count').textContent=`${matches.length} / ${source.length} 个 Rooms`;
  }
  function renderOverview(){
    const c=overview.counts;
    $('palace-counts').textContent=`${c.wings.toLocaleString()} 个 Wings · ${c.rooms.toLocaleString()} 个 Rooms · ${c.chunks.toLocaleString()} 个存储分块`;
    const select=$('palace-wing'),previous=select.value;
    select.replaceChildren(new document.defaultView.Option('全部 Wings',''));
    for(const w of overview.wings)select.append(new document.defaultView.Option(`${w.label} · ${w.rooms.length} Rooms`,w.id));
    if(overview.wings.some(w=>w.id===previous))select.value=previous;
    const d=overview.diagnostics||{},s=overview.sync||{};
    fields($('palace-diagnostics'),[
      ['索引后端',d.backend||'未报告'],['嵌入模型',s.embedding_model||'未报告'],
      ['向量检索',d.vector_disabled?'已停用 · 当前仅检查存储内容':'未报告停用'],
      ...(d.vector_disabled_reason?[['停用原因',d.vector_disabled_reason]]:[]),
      ...(d.sqlite_integrity_failed?[['存储完整性','检查失败']]:[]),
      ['已同步来源',`${s.delivered??0} 条`],['待同步来源',`${s.pending??0} 条`],
      ['引擎版本',s.revision||'未报告'],['结构读取时间',date(overview.read_at)],
    ]);
    rooms();
  }
  function renderPage(){
    const root=$('palace-list');root.replaceChildren();
    if(!page.drawers.length)root.append(el('p',page.wing||page.room?'当前范围没有记忆。':'宫殿里还没有记忆。','empty'));
    for(const item of page.drawers){
      const b=button('',()=>loadDetail(item.id),'palace-drawer');b.dataset.drawer=item.id;
      b.append(el('span',item.content_preview||'（空正文）','palace-preview'),
        el('small',`${item.source_file||'来源未记录'} · ${item.chunks} 分块`));
      b.setAttribute('aria-pressed',String(item.id===selected));root.append(b);
    }
    const begin=page.drawers.length?page.offset+1:0,end=page.offset+page.drawers.length;
    $('palace-page-status').textContent=`${wingLabel(page.wing)}${page.room?' / '+roomLabel(page.room):' / 全部房间'} · ${begin}–${end} / ${page.total.toLocaleString()} 条逻辑记忆`;
    rooms();controls();
  }
  async function loadPage(query){
    if(refreshing)return;
    const ticket=++pageRequest;listing=true;retryQuery={...query};
    $('palace-list-feedback').textContent=page?'正在读取所选范围，下面保留上次结果…':'正在读取记忆…';
    $('palace-list-retry').hidden=true;controls();
    const params=new URLSearchParams({limit:'20',offset:String(query.offset||0)});
    if(query.wing)params.set('wing',query.wing);
    if(query.room)params.set('room',query.room);
    try{
      const result=await api('memory/palace/drawers?'+params);
      if(ticket!==pageRequest)return;
      page=result;
      if($('palace-wing').value!==page.wing)$('palace-room-filter').value='';
      $('palace-wing').value=page.wing;
      selected='';++detailRequest;$('palace-detail').hidden=true;
      $('palace-list-feedback').textContent='';
      renderPage();
    }catch(error){
      if(ticket!==pageRequest)return;
      $('palace-list-feedback').textContent=`${error.message}${page?' 显示的仍是上次成功读取的结果。':''}`;
      $('palace-list-retry').hidden=false;
      if(page){$('palace-wing').value=page.wing;rooms();}
    }finally{if(ticket===pageRequest){listing=false;controls();}}
  }
  async function loadDetail(id){
    const ticket=++detailRequest;retryDetail=id;
    $('palace-detail').hidden=false;$('palace-detail-body').hidden=true;
    $('palace-detail-title').textContent=`原文详情 · ${id}`;
    $('palace-detail-feedback').textContent='正在读取原文…';$('palace-detail-retry').hidden=true;
    try{
      const item=await api('memory/palace/drawer?drawer_id='+encodeURIComponent(id));
      if(ticket!==detailRequest)return;
      selected=id;
      $('palace-list').querySelectorAll('[data-drawer]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.drawer===id)));
      $('palace-detail-feedback').textContent='';$('palace-detail-body').hidden=false;
      $('palace-original').textContent=item.content;
      fields($('palace-metadata'),[
        ['Drawer ID',item.id],['Wing',`${wingLabel(item.wing)} (${item.wing})`],['Room',item.room],
        ['来源',item.source_file||'未记录'],['入库时间',date(item.filed_at)],
        ['最后修改',date(item.last_modified)],['分块',item.chunks],
      ]);
      const sources=$('palace-sources');sources.replaceChildren();
      if(!item.sources.length)sources.append(el('p','未关联 mysoul 本地证据；显示的是 MemPalace 中的原文。','field-note'));
      for(const source of item.sources)sources.append(el('p',`${source.source} · ${source.id} · ${source.matches_original?'与本地原文一致':'与本地原文不一致'}`,source.matches_original?'field-note':'memory-error'));
      $('palace-chunk-ids').textContent=item.chunk_ids.length?item.chunk_ids.join('\n'):'单块记忆，无独立分块 ID。';
      $('palace-detail').scrollIntoView?.({block:'nearest'});
    }catch(error){if(ticket!==detailRequest)return;$('palace-detail-feedback').textContent=error.message;$('palace-detail-retry').hidden=false;}
  }
  async function refresh(){
    if(refreshing)return;
    const ticket=++overviewRequest;++pageRequest;++detailRequest;listing=false;refreshing=true;
    $('palace-detail').hidden=true;
    $('palace-list-feedback').textContent='';$('palace-list-retry').hidden=true;
    if(page)$('palace-wing').value=page.wing;
    controls();rooms();
    $('palace-feedback').textContent=overview?'正在刷新结构，保留上次结果…':'正在读取 MemPalace 原生结构…';
    try{
      const result=await api('memory/palace');
      if(ticket!==overviewRequest)return;
      overview=result;
      if(result.state!=='ready'){
        $('palace-content').hidden=true;$('palace-diagnostic-section').hidden=true;
        $('palace-counts').textContent='';
        $('palace-feedback').textContent=result.state==='not_configured'?'尚未接入 MemPalace，原生宫殿浏览暂不可用。':'当前引擎不支持完整的原生浏览接口。';
        page=null;return;
      }
      $('palace-content').hidden=false;$('palace-diagnostic-section').hidden=false;
      renderOverview();$('palace-feedback').textContent='';
    }catch(error){$('palace-feedback').textContent=`${error.message}${overview?' 上次读取的结构保留如下。':''}`;return;}
    finally{refreshing=false;controls();if(overview?.state==='ready')rooms();}
    const wing=$('palace-wing').value;
    const room=page?.wing===wing&&overview.wings.find(w=>w.id===wing)?.rooms.some(r=>r.id===page.room)?page.room:'';
    await loadPage({wing,room,offset:0});
  }
  $('palace-refresh').addEventListener('click',refresh);
  $('palace-wing').addEventListener('change',()=>{
    $('palace-room-filter').value='';rooms();loadPage({wing:$('palace-wing').value,room:'',offset:0});
  });
  $('palace-room-filter').addEventListener('input',rooms);
  $('palace-prev').addEventListener('click',()=>loadPage({...page,offset:Math.max(0,page.offset-page.limit)}));
  $('palace-next').addEventListener('click',()=>loadPage({...page,offset:page.offset+page.limit}));
  $('palace-list-retry').addEventListener('click',()=>loadPage(retryQuery));
  $('palace-detail-retry').addEventListener('click',()=>loadDetail(retryDetail));
  return {open:async()=>{if(!opened){opened=true;await refresh();}},refresh};
}
