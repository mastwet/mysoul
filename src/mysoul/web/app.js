"use strict";

import "/vendor/markdown-it.min.js";
import {createMessageRenderer, shouldSubmitKey} from "/conversation.mjs";

const renderMarkdown=createMessageRenderer(globalThis.markdownit);

const $ = (id) => document.getElementById(id);
const activityNames = {work:"工作", read_chat:"阅读聊天", read_news:"阅读新闻", rest:"休息", reflection:"反思"};
const modeNames = {normal:"日常", quiet:"安静", focused:"专注"};
const statusNames = {pending:"等待中", active:"进行中", suspended:"已暂停", completed:"已完成", failed:"失败", cancelled:"已取消", abandoned:"已放弃", confirmed:"已确认", unknown:"结果未知", not_sent:"未发送", in_flight:"进行中", draft:"草稿", proposed:"待测试", tested:"已测试", rejected:"已拒绝", active_skill:"已启用"};
const paths = {
  chat:["M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6A8.4 8.4 0 0 1 12.5 3h.5a8.5 8.5 0 0 1 8 8v.5Z"],
  tasks:["M9 5h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h1", "m8 3-2 2 2 2", "M8 12h9M8 16h6"],
  memory:["M12 7v14M3 3h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5v16h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z"],
  skills:["M14.7 6.3a5 5 0 0 0-6.5 6.5L3 18l3 3 5.2-5.2a5 5 0 0 0 6.5-6.5L14 13l-3-3Z"],
  settings:["M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z", "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0"],
  sidebar:["M9 3v18M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"],
  close:["m6 6 12 12M6 18 18 6"], up:["M12 19V5m-6 6 6-6 6 6"], down:["M12 5v14m-6-6 6 6 6-6"],
  plus:["M12 5v14M5 12h14"], edit:["m16 3 5 5-12 12-6 1 1-6Z", "m14 5 5 5"],
  copy:["M9 9h12v12H9Z", "M5 15H3V3h12v2"], check:["m5 12 4 4L19 6"],
  appearance:["M12 3a9 9 0 1 0 0 18 2 2 0 0 0 2-2c0-1-2-2-2-3s1-2 2-2h3a4 4 0 0 0 4-4c0-4-4-7-9-7Z", "M7 10h.01M10 6h.01M15 6h.01"],
  activity:["M3 12h4l3-8 4 16 3-8h4"], person:["M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0", "M4 21v-2a8 8 0 0 1 16 0v2"],
  connection:["M8 3v5m8-5v5M5 8h14v3a7 7 0 0 1-14 0ZM12 18v3"],
};
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key,value] of Object.entries({viewBox:"0 0 24 24", fill:"none", stroke:"currentColor", "stroke-width":"1.6", "stroke-linecap":"round", "stroke-linejoin":"round", "aria-hidden":"true"})) svg.setAttribute(key,value);
  for (const d of paths[name] || []) {const p=document.createElementNS(svg.namespaceURI,"path");p.setAttribute("d",d);svg.append(p);}
  return svg;
}
function node(tag, text, cls) {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
document.querySelectorAll("[data-icon]").forEach(el=>el.append(icon(el.dataset.icon)));
for (const [id,name] of Object.entries({"sidebar-close":"sidebar", "sidebar-toggle":"sidebar", "send-message":"up", "jump-bottom":"down", "dismiss-notice":"close"})) $(id).append(icon(name));
document.querySelectorAll("[data-close]").forEach(el=>el.append(icon("close")));

function readPreference(key, fallback) {try{return localStorage.getItem(key)??fallback;}catch{return fallback;}}
function savePreference(key, value) {try{localStorage.setItem(key,value);}catch{/* Storage may be unavailable in a restricted browser. */}}
const systemTheme = matchMedia("(prefers-color-scheme: dark)");
let theme = readPreference("mysoul-theme","light");
if(!["light","dark","system"].includes(theme))theme="light";
let enterSends = readPreference("mysoul-enter-send","true") !== "false";
function applyTheme() {document.documentElement.dataset.theme=theme==="system"?(systemTheme.matches?"dark":"light"):theme;}
applyTheme(); systemTheme.addEventListener("change",applyTheme);
$("theme").value=theme; $("enter-send").checked=enterSends;
$("theme").addEventListener("change",()=>{theme=$("theme").value;savePreference("mysoul-theme",theme);applyTheme();});
$("enter-send").addEventListener("change",()=>{enterSends=$("enter-send").checked;savePreference("mysoul-enter-send",String(enterSends));updateComposer();});

let token="";
try{token=sessionStorage.getItem("mysoul-token")||"";}catch{}
const fragment=new URLSearchParams(location.hash.slice(1));
if(fragment.has("token")){token=fragment.get("token");history.replaceState(null,"",location.pathname);}
let csrf="", snapshot=null, skillData=null, recapBase=null, activeView="chat";
let refreshPromise=null, pendingChat=null, chatSignature="", lifeDirty=false, loadedChat=false;
const busyScopes=new Set(), signatures=new WeakMap();

function notice(text) {
  const inSettings=$("settings-dialog").open;
  $("settings-feedback").hidden=!text||!inSettings;
  $("settings-feedback").textContent=inSettings?text:"";
  $("notice").hidden=!text||inSettings;
  $("notice-text").textContent=inSettings?"":text;
}
$("dismiss-notice").addEventListener("click",()=>notice(""));
async function api(path, body) {
  const headers={Authorization:`Bearer ${token}`};
  if(body!==undefined){headers["Content-Type"]="application/json";headers["X-CSRF-Token"]=csrf;}
  let response;
  try{response=await fetch(`/api/${path}`,{method:body===undefined?"GET":"POST",headers,body:body===undefined?undefined:JSON.stringify(body)});}
  catch{throw new Error("连接中断，请检查本地服务后重试。输入已保留。");}
  let result;try{result=await response.json();}catch{throw new Error("服务响应不可用，请稍后重试。");}
  if(!response.ok)throw new Error(response.status===409?"状态已变化或主体正忙，请稍后重试。当前输入已保留。":response.status===401?"操作令牌不可用，请使用启动时的本机访问链接。":typeof result.detail==="string"?result.detail:`请求失败（${response.status}）`);
  return result;
}
async function busy(element, action) {
  const scope=element.closest("[data-item]")||element.closest("form")||element;
  if(busyScopes.has(scope))return;
  busyScopes.add(scope);
  const controls=[...scope.querySelectorAll("button,input,textarea,select")];
  if(scope.matches("button"))controls.push(scope);
  const disabled=controls.map(control=>control.disabled);
  controls.forEach(control=>control.disabled=true);scope.setAttribute("aria-busy","true");
  try{notice("");await action();await refresh();}
  catch(error){notice(error.message);}
  finally{
    busyScopes.delete(scope);scope.removeAttribute("aria-busy");
    controls.forEach((control,i)=>control.disabled=disabled[i]);
    renderSnapshot(true);if(skillData)renderSkills(skillData,true);updateComposer();
  }
}
function bindForm(id, action) {$(id).addEventListener("submit",event=>{event.preventDefault();busy($(id),action);});}
function actionButton(label, action, primary=false) {const el=node("button",label,primary?"primary":"secondary");el.type="button";el.addEventListener("click",()=>busy(el,action));return el;}

// Keep unchanged rows and focused controls in place during background polling.
function keyedList(container, items, render, emptyText, force=false) {
  const previous=new Map([...container.children].filter(el=>el.dataset.key).map(el=>[el.dataset.key,el]));
  const keep=new Set();
  if(!items.length){
    if(container.dataset.empty!==emptyText){container.replaceChildren(node("p",emptyText,"empty"));container.dataset.empty=emptyText;}
    return;
  }
  if(container.dataset.empty!==undefined){container.replaceChildren();delete container.dataset.empty;}
  items.forEach((item,index)=>{
    const key=String(item.key), signature=JSON.stringify(item);let row=previous.get(key);
    const protectedRow=row&&(busyScopes.has(row)||(!force&&row.contains(document.activeElement)));
    if(!row||(signatures.get(row)!==signature&&!protectedRow)){
      const replacement=render(item);replacement.dataset.key=key;replacement.dataset.item="";
      signatures.set(replacement,signature);if(row)row.replaceWith(replacement);row=replacement;
    }
    keep.add(row);
    if(container.children[index]!==row)container.insertBefore(row,container.children[index]||null);
  });
  [...container.children].forEach(row=>{if(!keep.has(row)&&!busyScopes.has(row))row.remove();});
}

const mobile=matchMedia("(max-width: 820px)");
let sidebarCollapsed=readPreference("mysoul-sidebar-collapsed","false")==="true";
let mobileSidebar=false;
let settingsOpener=null;
function syncSidebar() {
  const open=mobile.matches?mobileSidebar:!sidebarCollapsed;
  $("workspace").classList.toggle("sidebar-collapsed",!mobile.matches&&sidebarCollapsed);
  $("workspace").classList.toggle("sidebar-open",mobile.matches&&open);
  $("sidebar").inert=!open;
  $("main-shell").inert=mobile.matches&&open;
  $("sidebar-backdrop").hidden=!mobile.matches||!open;
  $("sidebar-toggle").setAttribute("aria-expanded",String(open));
  $("sidebar-toggle").setAttribute("aria-label",open?"收起侧栏":"展开侧栏");
  if(mobile.matches&&open){$("sidebar").setAttribute("role","dialog");$("sidebar").setAttribute("aria-modal","true");}
  else{$("sidebar").removeAttribute("role");$("sidebar").removeAttribute("aria-modal");}
}
function closeSidebar() {if(mobile.matches)mobileSidebar=false;else{sidebarCollapsed=true;savePreference("mysoul-sidebar-collapsed","true");}syncSidebar();$("sidebar-toggle").focus();}
$("sidebar-toggle").addEventListener("click",()=>{if(mobile.matches){mobileSidebar=!mobileSidebar;}else{sidebarCollapsed=!sidebarCollapsed;savePreference("mysoul-sidebar-collapsed",String(sidebarCollapsed));}syncSidebar();if(mobileSidebar)$("sidebar-close").focus();});
$("sidebar-close").addEventListener("click",closeSidebar);
$("sidebar-backdrop").addEventListener("click",closeSidebar);
mobile.addEventListener("change",()=>{mobileSidebar=false;syncSidebar();});syncSidebar();
document.addEventListener("keydown",event=>{
  if(!mobileSidebar||!mobile.matches)return;
  if(event.key==="Escape"){event.preventDefault();closeSidebar();}
  if(event.key==="Tab"){
    const controls=[...$("sidebar").querySelectorAll("a,button:not(:disabled)")];
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});
function setView(view) {
  if(!["chat","tasks","memory","skills"].includes(view))return;
  activeView=view;
  document.querySelectorAll(".view").forEach(el=>el.hidden=el.id!==view);
  document.querySelectorAll("[data-view]").forEach(el=>{el.classList.toggle("active",el.dataset.view===view);if(el.dataset.view===view)el.setAttribute("aria-current","page");else el.removeAttribute("aria-current");});
  const title={chat:"mysoul",tasks:"任务",memory:"记忆",skills:"技能"}[view];
  $("page-title").textContent=title;document.title=`mysoul · ${view==="chat"?"对话":title}`;
  if(mobile.matches){mobileSidebar=false;syncSidebar();}
  if(view==="chat")requestAnimationFrame(()=>$("chat-text").focus());
  refresh();
}
document.querySelectorAll("[data-view]").forEach(el=>el.addEventListener("click",()=>setView(el.dataset.view)));

function selectSetting(name) {
  document.querySelectorAll("[data-setting]").forEach(el=>{const active=el.dataset.setting===name;el.classList.toggle("active",active);if(active)el.setAttribute("aria-current","page");else el.removeAttribute("aria-current");});
  document.querySelectorAll(".setting-page").forEach(el=>el.hidden=el.id!==`setting-${name}`);
  $("settings-content").scrollTop=0;
}
function openSettings(section="general") {
  settingsOpener=document.activeElement;
  if($("status-dialog").open)$("status-dialog").close();
  if(mobile.matches){mobileSidebar=false;syncSidebar();}
  notice("");selectSetting(section);$("settings-dialog").showModal();refresh();
}
$("open-settings").addEventListener("click",()=>openSettings());
$("status-settings").addEventListener("click",()=>openSettings("life"));
$("fatigue-card").addEventListener("click",()=>$("status-dialog").showModal());
$("settings-dialog").addEventListener("close",()=>{
  const visible=settingsOpener?.getClientRects().length&&!settingsOpener.closest("[inert]")&&!settingsOpener.closest("dialog:not([open])");
  (visible?settingsOpener:mobile.matches?$("sidebar-toggle"):$("fatigue-card")).focus();
});
document.querySelectorAll("[data-setting]").forEach(el=>el.addEventListener("click",()=>selectSetting(el.dataset.setting)));
document.querySelectorAll("[data-close]").forEach(el=>el.addEventListener("click",()=>$(el.dataset.close).close()));
for(const id of ["status-dialog","settings-dialog"]){
  $(id).addEventListener("click",event=>{if(event.target!==$(id))return;const box=$(id).getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)$(id).close();});
}

async function login() {
  try{
    csrf=(await api("session")).csrf;
    try{sessionStorage.setItem("mysoul-token",token);}catch{}
    $("login").hidden=true;$("workspace").hidden=false;syncSidebar();await refresh();
  }catch(error){$("login-error").textContent=error.message;$("login-error").hidden=false;}
}
bindForm("login-form",async()=>{token=$("token").value.trim();$("login-error").hidden=true;await login();});

async function refresh() {
  if(!csrf)return;
  if(refreshPromise)return refreshPromise;
  const requestedView=activeView;
  refreshPromise=(async()=>{
    try{
      snapshot=await api("status");
      $("connection").textContent="已连接 · 本机";document.querySelector(".connection-dot").classList.remove("offline");
      renderSnapshot();
      if(requestedView==="memory"){
        const [evidence,history]=await Promise.all([api("evidence"),api("recap/history")]);
        if(activeView===requestedView){renderEvidence(evidence);renderHistory(history);}
      }else if(requestedView==="skills"){
        const [skills,evidence]=await Promise.all([api("skills"),api("evidence")]);
        if(activeView===requestedView){skillData=skills;renderSkills(skills);renderEvidenceOptions(evidence);}
      }
    }catch(error){$("connection").textContent="连接中断";document.querySelector(".connection-dot").classList.add("offline");notice(error.message);}
    finally{refreshPromise=null;if(activeView!==requestedView)queueMicrotask(refresh);}
  })();
  return refreshPromise;
}
function renderSnapshot(force=false) {
  if(!snapshot)return;
  const state=snapshot.state, percent=Math.round(state.fatigue*100), activity=activityNames[state.activity]||state.activity;
  $("runtime-label").textContent=snapshot.backend==="replay"?"离线回放":"真实通道";
  $("activity").textContent=activity;$("status-activity").textContent=activity;
  $("fatigue-label").textContent=`${percent}%`;$("status-fatigue").textContent=`${percent}%`;
  $("fatigue-meter").value=state.fatigue;$("fatigue-card").setAttribute("aria-label",`疲劳 ${percent}%，查看状态`);
  $("fatigue-card").classList.toggle("high",state.fatigue>=.6);
  $("fatigue-description").textContent=state.fatigue>=.9?"建议休息，主动活动会受限制。":state.fatigue>=.6?"适合放慢节奏，休息会逐渐恢复。":"精力充足，可以自然安排活动。";
  $("mode-label").textContent=modeNames[state.mode];
  const limits=snapshot.limits||{};
  $("calls").textContent=state.model_calls.toLocaleString();$("tokens").textContent=state.tokens_used.toLocaleString();
  for(const [id,value,limit] of [["calls",state.model_calls,limits.model_calls],["tokens",state.tokens_used,limits.tokens]]){
    $(`budget-${id}`).textContent=`${value.toLocaleString()}${limit===undefined?"":` / ${limit.toLocaleString()}`}`;
    $(`${id}-meter`).max=Math.max(1,limit??value);$(`${id}-meter`).value=value;
  }
  if(!lifeDirty&&!busyScopes.has($("life-form"))){$("mode").value=state.mode;$("fatigue-input").value=percent;$("fatigue-range").value=percent;}
  $("persona-view").textContent=snapshot.persona.public;
  $("recap-version").textContent=`v${snapshot.recap.version}`;
  $("recap-view").textContent=snapshot.recap.text||"还没有摘要。新的经验会在整理后出现在这里。";
  const activeTasks=snapshot.goals.filter(g=>["pending","active","suspended"].includes(g.status)).length;
  $("task-count").textContent=activeTasks;$("task-count").hidden=!activeTasks;
  $("connection-description").textContent=snapshot.backend==="replay"?"当前使用离线回放。真实模型、长期记忆和 QQ 尚待验收。":`QQ 通道已配置。真实发送${snapshot.send_enabled?"已启用，仍受白名单与权限检查约束":"未启用，当前仅观察或保留草稿"}。`;
  const gateNames={provider:"模型服务",mempalace:"长期记忆",qq:"QQ 通道",isolation:"代码执行"};
  keyedList($("gates"),Object.entries(snapshot.gates).map(([key,value])=>({key,value})),item=>{const li=node("li");li.append(node("b",gateNames[item.key]),node("span",item.value==="disabled"?"未启用":item.value==="deferred"?"待验收":item.value));return li;},"",force);
  renderMessages(snapshot.interactions);renderRecent(snapshot.interactions);renderJobs(snapshot,force);
}

function nearBottom() {const el=$("conversation-scroll");return el.scrollHeight-el.scrollTop-el.clientHeight<90;}
function scrollBottom() {const el=$("conversation-scroll");el.scrollTop=el.scrollHeight;$("jump-bottom").hidden=true;}
$("conversation-scroll").addEventListener("scroll",()=>$("jump-bottom").hidden=nearBottom()||$("chat-empty").hidden===false);
$("jump-bottom").addEventListener("click",scrollBottom);
function messageBody(text) {
  const body=node("div",undefined,"message-body");
  // Only the pinned html:false renderer may produce HTML. Remote images are text-only.
  body.innerHTML=renderMarkdown(text);
  return body;
}
function renderTurn(item) {
  const row=node("article",undefined,"message-turn");row.id=`turn-${item.key}`;
  if(item.input){const user=node("div",undefined,"user-message");const bubble=node("div",undefined,"user-bubble");if(item.choice!=="owner_served"&&!item.pending)bubble.append(node("div","外部消息","source-label"));bubble.append(document.createTextNode(item.input));user.append(bubble);row.append(user);}
  const reply=node("div",undefined,"assistant-message"),meta=node("div",undefined,"assistant-meta");
  meta.append(node("span","m","assistant-mark"),node("strong","mysoul"));
  if(!["owner_served",undefined].includes(item.choice))meta.append(node("span",{sent:"已发送",draft:"草稿 · 未发送",unknown:"发送结果未知",silent:"阅读 · 保持沉默"}[item.choice]||""));
  reply.append(meta);
  if(item.pending){const thinking=node("div",undefined,"thinking");thinking.setAttribute("role","status");thinking.append(node("i"),node("i"),node("i"),node("span","正在回应…"));reply.append(thinking);}
  else if(item.text){
    reply.append(messageBody(item.text));
    const actions=node("div",undefined,"message-actions"),copy=node("button",undefined,"icon-button");copy.type="button";copy.setAttribute("aria-label","复制回复");copy.append(icon("copy"));
    copy.addEventListener("click",async()=>{try{await navigator.clipboard.writeText(item.text);copy.replaceChildren(icon("check"));copy.setAttribute("aria-label","已复制");}catch{notice("复制不可用，请选中回复后手动复制。");}});actions.append(copy);reply.append(actions);
  }else reply.append(node("p","已保留这条消息，没有发出回复。","muted"));
  row.append(reply);return row;
}
function renderMessages(interactions) {
  const items=interactions.map(item=>({...item,key:item.event_id}));if(pendingChat)items.push({...pendingChat,key:"pending",pending:true});
  const signature=JSON.stringify(items);if(signature===chatSignature)return;chatSignature=signature;
  const stick=!loadedChat||nearBottom();loadedChat=true;
  $("chat-empty").hidden=items.length>0;$("messages").hidden=!items.length;
  keyedList($("messages"),items,renderTurn,"");
  if(stick)requestAnimationFrame(scrollBottom);else $("jump-bottom").hidden=false;
}
function renderRecent(interactions) {
  const items=interactions.filter(item=>item.choice==="owner_served"&&item.input).slice(-12).reverse().map(item=>({key:item.event_id,text:item.input}));
  keyedList($("recent-messages"),items,item=>{const b=node("button",item.text);b.type="button";b.title=item.text;b.addEventListener("click",()=>{setView("chat");requestAnimationFrame(()=>$("turn-"+item.key)?.scrollIntoView({block:"center"}));});return b;},"还没有消息");
}
function renderJobs(state,force) {
  keyedList($("jobs"),state.goals.slice().reverse().map(goal=>({key:goal.id,goal,activity:state.activities.filter(a=>a.goal_id===goal.id).at(-1)})),item=>{
    const row=node("article",undefined,"job"),heading=node("div",undefined,"job-title"),{goal,activity}=item;
    heading.append(node("strong",goal.objective),node("span",statusNames[goal.status]||goal.status,"badge"));row.append(heading);
    if(activity)row.append(node("p",`已执行 ${activity.cursor} 步 · 固定技能 ${activity.skill_version.slice(0,8)}`,"muted"));
    const actions=node("div",undefined,"actions");
    if(activity?.status==="suspended")for(const [decision,label] of [["continue","继续"],["replan","重规划"],["abandon","放弃"]])actions.append(actionButton(label,()=>api(`activities/${encodeURIComponent(activity.id)}/resume`,{decision})));
    if(["pending","active","suspended"].includes(goal.status))actions.append(actionButton("取消任务",()=>api(`goals/${encodeURIComponent(goal.id)}/cancel`,{})));
    if(actions.childNodes.length)row.append(actions);return row;
  },"还没有任务。在上方写下一个有明确完成条件的目标。",force);
  const effects=[...(state.effects||[]).map(result=>({key:result.action_id,result})),...state.drafts.map((draft,i)=>({key:"draft:"+(draft.id||i),draft}))];
  keyedList($("effects"),effects,item=>{const row=node("div",undefined,"evidence-row");if(item.draft){row.append(node("small","草稿 · 尚未发送"),node("p",item.draft.text));}else{const r=item.result;row.append(node("strong",statusNames[r.outcome]||r.outcome),node("p",r.content||r.error||r.receipt||"已记录动作结果"));if(r.outcome==="unknown")row.append(actionButton("查询回执",()=>api(`effects/${encodeURIComponent(r.action_id)}/reconcile`,{})));}return row;},"还没有动作记录。任务产物、回执与草稿会保留在这里。",force);
}
function renderEvidence(evidence) {
  keyedList($("evidence"),evidence.slice(0,30).map(e=>({...e,key:e.id})),e=>{const row=node("div",undefined,"evidence-row");row.append(node("small",`${e.scope.audience==="owner"?"私有":e.scope.audience==="group"?"群聊":"公开"} · ${e.source} · ${new Date(e.created_at).toLocaleString()}`),node("p",e.text.slice(0,500)));return row;},"还没有来源证据。对话和任务产生的经验会保留在这里。");
}
function renderHistory(history) {
  keyedList($("recap-history"),history.map(v=>({...v,key:v.version})),v=>{const row=node("div",undefined,"history-row");row.append(node("strong",`v${v.version} · ${new Date(v.created_at).toLocaleString()}`),node("p",v.text.slice(0,160)||"空摘要"));return row;},"还没有历史版本。");
}
function renderEvidenceOptions(evidence) {
  if(busyScopes.has($("proposal-form"))||document.activeElement===$("evidence-select"))return;
  const select=$("evidence-select"),signature=JSON.stringify(evidence.map(e=>[e.id,e.text.slice(0,70)]));if(signatures.get(select)===signature)return;
  const selected=select.value;select.replaceChildren(...evidence.map(e=>{const option=node("option",e.text.slice(0,70)||e.source);option.value=e.id;return option;}));
  if(evidence.some(e=>e.id===selected))select.value=selected;
  signatures.set(select,signature);$("reflect").disabled=!evidence.length;
}
function renderSkills(data,force=false) {
  $("skill-version").textContent=data.active.content_hash.slice(0,10);$("skill-view").textContent=data.active.text;
  const review=data.proposals.filter(p=>["proposed","tested","approved"].includes(p.status)).length;$("review-count").textContent=review;$("review-count").hidden=!review;
  if(!busyScopes.has($("rollback-form"))&&document.activeElement!==$("rollback-select")){
    const select=$("rollback-select"),signature=JSON.stringify(data.versions.map(v=>v.content_hash));
    if(signatures.get(select)!==signature){const selected=select.value;select.replaceChildren(...data.versions.map(v=>{const option=node("option",`${v.content_hash.slice(0,10)} · ${new Date(v.activated_at).toLocaleString()}`);option.value=v.content_hash;return option;}));if(data.versions.some(v=>v.content_hash===selected))select.value=selected;signatures.set(select,signature);}
  }
  keyedList($("proposals"),data.proposals.slice().reverse().map(p=>({...p,key:p.id,runs:data.tests.filter(t=>p.test_run_ids.includes(t.id))})),p=>{
    const row=node("article",undefined,"proposal"),heading=node("div",undefined,"job-title");heading.append(node("strong",`工作技能 · ${p.candidate_hash.slice(0,8)}`),node("span",p.status==="active"?"已启用":statusNames[p.status]||p.status,"badge"));row.append(heading,node("pre",p.diff,"diff"));
    for(const run of p.runs){
      const result=node("div",undefined,"test-result");result.append(node("strong",`客观断言：${run.objective_pass?"通过":"失败"}`));
      if(run.baseline)result.append(node("p",`基础版本：${run.baseline.every(r=>r.objective_pass)?"通过":"失败"} · 候选版本：${run.objective_pass?"通过":"失败"}`,"muted"));
      result.append(node("p",`模型评价：${run.model_judgment||"未提供"}\n测试模型：${run.model_label||"procedure-replay"} · 独立工作区，发送通道关闭`,"muted"));
      if(run.cases){const details=node("details"),summary=node("summary","查看测试条件与产物");details.append(summary,node("pre",JSON.stringify({cases:run.cases,baseline:run.baseline,candidate:run.candidate},null,2),"diff"));result.append(details);}
      row.append(result);
    }
    const actions=node("div",undefined,"actions");if(["proposed","tested"].includes(p.status)){
      actions.append(actionButton("运行候选测试",()=>api(`skills/${encodeURIComponent(p.id)}/test`,{})));
      if(p.runs.length&&p.runs.every(r=>r.objective_pass))actions.append(actionButton("审核并启用",()=>api(`skills/${encodeURIComponent(p.id)}/approve`,{expected_base_hash:p.base_hash,approved_candidate_hash:p.candidate_hash}),true));
      actions.append(actionButton("拒绝提案",()=>api(`skills/${encodeURIComponent(p.id)}/reject`,{})));
    }if(actions.childNodes.length)row.append(actions);return row;
  },"没有待审核的提案。积累经验后，可以基于证据反思或提交改进。",force);
}

function updateComposer() {
  $("send-message").disabled=!$("chat-text").value.trim()||!!pendingChat;
  $("composer-hint").textContent=enterSends?"Enter 发送，Shift + Enter 换行":"Ctrl / ⌘ + Enter 发送";
  const textarea=$("chat-text");textarea.style.height="auto";textarea.style.height=`${Math.min(textarea.scrollHeight,170)}px`;
}
$("chat-text").addEventListener("input",updateComposer);
$("chat-text").addEventListener("keydown",event=>{
  if(shouldSubmitKey(event,enterSends)){event.preventDefault();if(!$("send-message").disabled)$("chat-form").requestSubmit();}
});
bindForm("chat-form",async()=>{
  const input=$("chat-text"),text=input.value;if(!text.trim()||pendingChat)return;
  pendingChat={input:text,choice:"owner_served"};renderMessages(snapshot?.interactions||[]);scrollBottom();
  try{
    const result=await api("chat",{text});
    pendingChat=null;input.value="";
    if(snapshot&&!snapshot.interactions.some(item=>item.event_id===result.event_id))snapshot.interactions.push(result);
    renderMessages(snapshot?.interactions||[]);await refresh();
  }
  finally{pendingChat=null;renderMessages(snapshot?.interactions||[]);updateComposer();}
});
document.querySelectorAll("[data-prompt]").forEach(el=>el.addEventListener("click",()=>{$("chat-text").value=el.dataset.prompt;updateComposer();$("chat-text").focus();}));
bindForm("goal-form",async()=>{await api("goals",{text:$("goal-text").value});$("goal-text").value="";});
$("mode").addEventListener("change",()=>{lifeDirty=true;$("life-saved").textContent="";});
for(const id of ["fatigue-input","fatigue-range"]){$(id).addEventListener("input",()=>{lifeDirty=true;$(id==="fatigue-input"?"fatigue-range":"fatigue-input").value=$(id).value;$("life-saved").textContent="";});}
bindForm("life-form",async()=>{await api("life",{mode:$("mode").value,fatigue:Number($("fatigue-input").value)/100});lifeDirty=false;$("life-saved").textContent="已保存";});
$("edit-recap").addEventListener("click",()=>{recapBase=snapshot.recap;$("recap-text").value=recapBase.text;$("recap-form").hidden=false;$("recap-actions").hidden=true;$("recap-view").hidden=true;$("recap-text").focus();});
function closeRecap(){$("recap-form").hidden=true;$("recap-actions").hidden=false;$("recap-view").hidden=false;}
$("cancel-recap").addEventListener("click",closeRecap);
bindForm("recap-form",async()=>{await api("recap",{expected_version:recapBase.version,text:$("recap-text").value,refs:recapBase.refs});closeRecap();});
$("clear-recap").addEventListener("click",()=>busy($("clear-recap"),()=>api("recap/clear",{expected_version:snapshot.recap.version})));
$("edit-persona").addEventListener("click",()=>{$("persona-text").value=snapshot.persona.public;$("persona-form").hidden=false;$("persona-view").hidden=true;$("edit-persona").hidden=true;$("persona-text").focus();});
function closePersona(){$("persona-form").hidden=true;$("persona-view").hidden=false;$("edit-persona").hidden=false;}
$("cancel-persona").addEventListener("click",closePersona);
bindForm("persona-form",async()=>{await api("persona",{public:$("persona-text").value});closePersona();});
bindForm("proposal-form",async()=>{await api("skills/propose",{text:$("candidate-text").value,evidence_refs:[$("evidence-select").value]});$("candidate-text").value="";});
$("reflect").addEventListener("click",()=>busy($("proposal-form"),()=>api("reflection",{evidence_refs:[$("evidence-select").value]})));
bindForm("rollback-form",()=>api("skills/rollback",{target_version:$("rollback-select").value}));
if(token)login();
setInterval(()=>{if(!document.hidden)refresh();},2500);
