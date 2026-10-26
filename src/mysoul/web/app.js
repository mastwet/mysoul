"use strict";

import "/vendor/markdown-it.min.js";
import {createMessageRenderer, shouldSubmitKey} from "/conversation.mjs";
import {mergeTimeline, prependScrollAnchor} from "/timeline.mjs";
import {createPalaceBrowser} from "/palace.mjs";
import {createInnerVoice} from "/inner-voice.mjs";

const renderMarkdown=createMessageRenderer(globalThis.markdownit);

const $ = (id) => document.getElementById(id);
const activityNames = {work:"工作", read_chat:"阅读聊天", read_news:"阅读新闻", rest:"休息", reflection:"反思"};
const modeNames = {normal:"日常", quiet:"安静", focused:"专注"};
const failureNames = {
  timeout:"请求超时", context_limit:"上下文超过模型服务容量", context_budget:"超出本机上下文预算",
  authentication:"密钥或账号权限有误", rate_limit:"模型服务限流", model_unavailable:"模型或接口不可用",
  connection:"无法连接模型服务", invalid_response:"模型返回格式无法识别", response_limit:"模型响应超过安全上限",
  provider_error:"模型服务返回错误",
};
const personaNames = {
  identity:"身份与表达", relationship:"与主人关系", redline:"边界与原则", user:"主人资料",
  world:"认识世界的方式", dream:"愿望与成长方向", dark:"私密内在", mission:"持续使命",
};
const statusNames = {pending:"等待中", active:"进行中", suspended:"已暂停", completed:"已完成", failed:"失败", cancelled:"已取消", abandoned:"已放弃", confirmed:"已确认", unknown:"结果未知", not_sent:"未发送", in_flight:"进行中", draft:"草稿", proposed:"待测试", tested:"已测试", rejected:"已拒绝", active_skill:"已启用"};
const paths = {
  voice:["M5 5h14v10H9l-4 4V5Z","M8 9h8M8 12h5"],
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
let timelineItems=[], timelineCursor=0, olderCursor=null, historyReady=false, historyLoading=false;
let archiveState=null;
let sessionRevision=null, historyGeneration=0, chatAbort=null, resetExpectedVersion=0;
const innerVoice=createInnerVoice({document,api});
let modelDirty=false, modelVersion=0, personaEditVersion=0;
let cognitionDirty=false,cognitionEditVersion=0;
const busyScopes=new Set(), signatures=new WeakMap();

function notice(text) {
  const inSettings=$("settings-dialog").open;
  $("settings-feedback").hidden=!text||!inSettings;
  $("settings-feedback").textContent=inSettings?text:"";
  $("notice").hidden=!text||inSettings;
  $("notice-text").textContent=inSettings?"":text;
}
$("dismiss-notice").addEventListener("click",()=>notice(""));
async function api(path, body, signal) {
  const headers=token?{Authorization:`Bearer ${token}`} : {};
  if(body!==undefined){headers["Content-Type"]="application/json";headers["X-CSRF-Token"]=csrf;}
  let response;
  try{response=await fetch(`/api/${path}`,{signal,method:body===undefined?"GET":"POST",headers,body:body===undefined?undefined:JSON.stringify(body)});}
  catch{throw new Error("连接中断，请检查本地服务后重试。输入已保留。");}
  let result;try{result=await response.json();}catch{throw new Error("服务响应不可用，请稍后重试。");}
  if(!response.ok)throw Object.assign(new Error(response.status===409?"状态已变化或主体正忙，请稍后重试。当前输入已保留。":response.status===401?"操作令牌不可用，请使用启动时的本机访问链接。":typeof result.detail==="string"?result.detail:`请求失败（${response.status}）`),{status:response.status});
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
    if(scope===$("chat-form")&&activeView==="chat"&&document.activeElement===document.body
        &&!$("settings-dialog").open&&!$("status-dialog").open){
      $("chat-text").focus({preventScroll:true});
    }
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
  if(!["chat","inner-voice","tasks","memory","persona","skills"].includes(view))return;
  activeView=view;
  document.querySelectorAll(".view").forEach(el=>el.hidden=el.id!==view);
  document.querySelectorAll("[data-view]").forEach(el=>{el.classList.toggle("active",el.dataset.view===view);if(el.dataset.view===view)el.setAttribute("aria-current","page");else el.removeAttribute("aria-current");});
  innerVoice.setActive(view==="inner-voice");
  const title={chat:"mysoul","inner-voice":"心语",tasks:"任务",memory:"记忆",persona:"人格",skills:"技能"}[view];
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
$("initiative-status").addEventListener("click",()=>openSettings("life"));
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

async function login(automatic=false) {
  try{
    const session=await api("session");csrf=session.csrf;
    if(session.auth_required===false)token="";
    try{if(token)sessionStorage.setItem("mysoul-token",token);else sessionStorage.removeItem("mysoul-token");}catch{}
    $("login").hidden=true;$("workspace").hidden=false;syncSidebar();await refresh();
  }catch(error){if(automatic&&!token&&error.status===401)return;$("login-error").textContent=error.message;$("login-error").hidden=false;}
}
bindForm("login-form",async()=>{token=$("token").value.trim();$("login-error").hidden=true;await login();});

async function refresh() {
  if(!csrf)return;
  if(refreshPromise)return refreshPromise;
  const requestedView=activeView,requestedGeneration=historyGeneration;
  refreshPromise=(async()=>{
    try{
      const next=await api("status");
      if(requestedGeneration!==historyGeneration)return;
      snapshot=next;
      $("connection").textContent="已连接 · 本机";document.querySelector(".connection-dot").classList.remove("offline");
      const previousNotice=$("notice-text").textContent||$("settings-feedback").textContent;
      if(previousNotice.startsWith("连接中断"))notice("");
      renderSnapshot();
      await pollTimeline();
      if(requestedView==="memory"){
        const [evidence,history,personaHistory,archives]=await Promise.all([api("evidence"),api("recap/history"),api("persona/history"),api("archives")]);
        if(activeView===requestedView){renderEvidence(evidence);renderHistory(history);renderPersonaHistory(personaHistory);renderMemoryStatus();renderArchives(archives);}
      }else if(requestedView==="inner-voice"){
        await innerVoice.refresh();
      }else if(requestedView==="persona"){
        await loadPersonaHistory();
      }else if(requestedView==="skills"){
        const [skills,evidence]=await Promise.all([api("skills"),api("evidence")]);
        if(activeView===requestedView){skillData=skills;renderSkills(skills);renderEvidenceOptions(evidence);}
      }
    }catch(error){$("connection").textContent="连接中断";document.querySelector(".connection-dot").classList.add("offline");notice(error.message);}
    finally{refreshPromise=null;if(activeView!==requestedView||requestedGeneration!==historyGeneration)queueMicrotask(refresh);}
  })();
  return refreshPromise;
}
function renderSnapshot(force=false) {
  if(!snapshot)return;
  const conversation=snapshot.conversation||{revision:0};
  $("conversation-info").textContent=conversation.revision?`已归档 ${conversation.revision} 次，旧聊天原文保存在本机。`:"还没有重置记录。";
  if(!$("download-conversation-archive").dataset.loading)$("download-conversation-archive").disabled=!conversation.revision;
  const state=snapshot.state, percent=Math.round(state.fatigue*100), activity=activityNames[state.activity]||state.activity;
  const model=snapshot.model;
  const modelLabel=model.mode==="provider"?`真实模型 · ${model.model}`:model.mode==="procedure-replay"?"离线流程演示":"离线回放";
  $("runtime-label").textContent=modelLabel;
  $("model-current").textContent=`当前：${modelLabel}${model.source==="local"?" · 已保存在本机":model.source==="environment"?" · 环境变量配置":""}`;
  $("reset-model").hidden=!modelDirty;
  if(!modelDirty&&!busyScopes.has($("model-form"))){
    modelVersion=model.version;$("model-mode").value=model.mode;$("model-url").value=model.url;$("model-name").value=model.model;
    $("model-output-limit").value=model.output_token_limit??"";$("model-token-budget").value=model.token_budget??"";
    $("model-context-chars").value=model.context_chars;$("model-timeout").value=model.request_timeout;
    $("model-key").placeholder=model.key_present?"已保存密钥，留空表示保留":"填写模型服务的 API Key";
    $("model-key-note").textContent=model.key_present?"密钥已配置，不会回显。更改 API 地址时，请重新填写密钥。":"与本机操作令牌不同。密钥保存在本机，不会回显。";
    syncModelFields();
  }
  $("activity").textContent=activity;$("status-activity").textContent=activity;
  $("fatigue-label").textContent=`${percent}%`;$("status-fatigue").textContent=`${percent}%`;
  $("fatigue-meter").value=state.fatigue;$("fatigue-card").setAttribute("aria-label",`疲劳 ${percent}%，查看状态`);
  $("fatigue-card").classList.toggle("high",state.fatigue>=.6);
  $("fatigue-description").textContent=state.fatigue>=.9?"建议休息，主动活动会受限制。":state.fatigue>=.6?"适合放慢节奏，休息会逐渐恢复。":"精力充足，可以自然安排活动。";
  $("mode-label").textContent=modeNames[state.mode];
  const limits=snapshot.limits||{};
  $("calls").textContent=state.model_calls.toLocaleString();$("tokens").textContent=state.tokens_used.toLocaleString();
  for(const [id,value,limit] of [["calls",state.model_calls,limits.model_calls],["tokens",state.tokens_used,limits.tokens]]){
    $(`budget-${id}`).textContent=`${value.toLocaleString()}${limit===null?" / 不限":limit===undefined?"":` / ${limit.toLocaleString()}`}`;
    $(`${id}-meter`).hidden=limit===null;
    $(`${id}-meter`).max=Math.max(1,limit??value);$(`${id}-meter`).value=value;
  }
  if(!lifeDirty&&!busyScopes.has($("life-form"))){$("mode").value=state.mode;$("fatigue-input").value=percent;$("fatigue-range").value=percent;$("autonomy-enabled").checked=state.autonomy_enabled;$("autonomy-interval").value=String(state.autonomy_interval_minutes);}
  const initiativeCadence=state.autonomy_interval_minutes<60?state.autonomy_interval_minutes+" 分钟":state.autonomy_interval_minutes/60+" 小时";
  let initiativeOutcome={waiting:state.autonomy_last_checked_at?"正在检查":"等待首次检查",silent:"上次保持安静",message:"最近已主动发起",error:"上次检查失败",interrupted:"主人输入打断了检查",paused:"设置变化后已停止"}[state.autonomy_last_result]||"等待检查";
  const initiative=snapshot.initiative;
  const initiativeError=initiative?.error;
  if(state.autonomy_last_result==="error"&&initiativeError)initiativeOutcome+=`（${failureNames[initiativeError.code]||initiativeError.code}）`;
  const backgroundNote=initiative?.background_goal_id?" · 后台任务："+({running:"正在推进",yield:"已保存进度，等待下次检查",completed:"已完成，尚未自动发言",blocked:"需要处理后继续",owner:"已让出给主人",deferred:"等待合适时机",cancelled:"已取消",abandoned:"已放弃"}[initiative.background_status]||initiative.background_status||"等待处理"):"";
  $("initiative-detail").textContent=initiativeError?initiativeError.message:initiative?.outcome==="waiting"?"正在检查，完成后会显示决策原因。":(initiative?.reason||"最近一次检查尚无详细记录。")+backgroundNote;
  let initiativePauseReason=state.mode!=="normal"?modeNames[state.mode]+"模式":state.fatigue>=.9?"疲劳过高":limits.model_calls!==null&&limits.model_calls!==undefined&&state.model_calls>=limits.model_calls?"调用预算已用尽":limits.tokens!==null&&limits.tokens!==undefined&&state.tokens_used>=limits.tokens?"Token预算已用尽":"";
  const cadenceNote=snapshot.scheduled_wakeup?"本体安排 · "+new Date(snapshot.scheduled_wakeup.due_at).toLocaleString("zh-CN",{hour12:false})+"唤醒":"每 "+initiativeCadence+"检查";
  $("initiative-status").textContent=!state.autonomy_enabled?"自主发起已暂停 · "+initiativeOutcome:initiativePauseReason?"自主发起暂停 · "+initiativePauseReason+" · "+initiativeOutcome:"自主活动已开启 · "+cadenceNote+" · "+initiativeOutcome;
  renderCognition();
  renderPersonaSections();
  $("persona-view").textContent=snapshot.persona.public;
  $("persona-version").textContent=`当前版本 v${snapshot.persona.version} · 新版本用于后续对话，活动中的任务保留原版本`;
  $("recap-version").textContent=`v${snapshot.recap.version}`;
  $("recap-view").textContent=snapshot.recap.text||"还没有摘要。新的经验会在整理后出现在这里。";
  const activeTasks=snapshot.goals.filter(g=>["pending","active","suspended"].includes(g.status)).length;
  $("task-count").textContent=activeTasks;$("task-count").hidden=!activeTasks;
  $("connection-description").textContent=`模型：${modelLabel}。${snapshot.backend==="replay"?"QQ 使用离线回放。":`QQ 通道已配置，真实发送${snapshot.send_enabled?"已启用":"未启用"}。`}下方为完整集成验收状态，保存配置或连接测试不会自动通过验收。`;
  const gateNames={provider:"模型服务",mempalace:"长期记忆",qq:"QQ 通道",isolation:"代码执行"};
  keyedList($("gates"),Object.entries(snapshot.gates).map(([key,value])=>({key,value})),item=>{const li=node("li");li.append(node("b",gateNames[item.key]),node("span",item.value==="disabled"?"未启用":item.value==="deferred"?"待验收":item.value));return li;},"",force);
  renderMessages(false,force);renderJobs(snapshot,force);
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
  const row=node("article",undefined,"message-turn");row.id=`turn-${item.event_id||item.key}`;
  if(item.input){const user=node("div",undefined,"user-message");const bubble=node("div",undefined,"user-bubble");if(item.choice!=="owner_served"&&!item.pending)bubble.append(node("div","外部消息","source-label"));bubble.append(document.createTextNode(item.input));user.append(bubble);row.append(user);}
  const reply=node("div",undefined,"assistant-message"),meta=node("div",undefined,"assistant-meta");
  meta.append(node("span","m","assistant-mark"),node("strong","mysoul"));
  if(!["owner_served",undefined].includes(item.choice))meta.append(node("span",{sent:"已发送",draft:"草稿 · 未发送",unknown:"发送结果未知",silent:"阅读 · 保持沉默",initiative:"主动发起"}[item.choice]||""));
  reply.append(meta);
  if(item.pending){const thinking=node("div",undefined,"thinking");thinking.setAttribute("role","status");thinking.append(node("i"),node("i"),node("i"),node("span","正在回应…"));reply.append(thinking);}
  else if(item.error){
    const failure=node("div",undefined,"chat-failure");
    const code=item.error.code||"provider_error";
    failure.append(node("strong",`未能生成回复 · ${failureNames[code]||code} (${code})`),node("p",item.error.message||item.text||"模型服务暂时无法完成请求。"));
    reply.append(failure);
  }
  else if(item.text==="Model unavailable"){
    const failure=node("div",undefined,"chat-failure");
    failure.append(node("strong","旧版请求失败 · 当时原因未记录"),node("p","这条历史记录没有保留服务端错误细节。新请求会显示超时、上下文容量、密钥或接口问题等具体原因。"));
    reply.append(failure);
  }
  else if(item.text){
    reply.append(messageBody(item.text));
    const actions=node("div",undefined,"message-actions"),copy=node("button",undefined,"icon-button");copy.type="button";copy.setAttribute("aria-label","复制回复");copy.append(icon("copy"));
    copy.addEventListener("click",async()=>{try{await navigator.clipboard.writeText(item.text);copy.replaceChildren(icon("check"));copy.setAttribute("aria-label","已复制");}catch{notice("复制不可用，请选中回复后手动复制。");}});actions.append(copy);reply.append(actions);
  }else reply.append(node("p","已保留这条消息，没有发出回复。","muted"));
  row.append(reply);return row;
}
function resetConversationView(revision,clearDraft=false){
 sessionRevision=revision;historyGeneration++;chatAbort?.abort();pendingChat=null;
 timelineItems=[];timelineCursor=0;olderCursor=null;historyReady=false;chatSignature="";loadedChat=false;
 $("load-older").hidden=true;$("history-feedback").textContent="";$("jump-bottom").hidden=true;
 recapBase=null;$("recap-form").hidden=true;$("recap-view").hidden=false;$("recap-actions").hidden=false;$("recap-text").value="";
 if(clearDraft)$("chat-text").value="";
 renderMessages();updateComposer();
}
$("reset-conversation").addEventListener("click",()=>{
 resetExpectedVersion=snapshot?.conversation?.revision??sessionRevision??0;
 $("conversation-reset-confirm").hidden=false;$("conversation-feedback").textContent="";
});
$("cancel-conversation-reset").addEventListener("click",()=>{$("conversation-reset-confirm").hidden=true;});
$("confirm-conversation-reset").addEventListener("click",async()=>{
 const button=$("confirm-conversation-reset");if(button.disabled)return;
 button.disabled=true;$("cancel-conversation-reset").disabled=true;$("reset-conversation").disabled=true;
 try{
  const result=await api("conversation/reset",{expected_version:resetExpectedVersion});
  resetConversationView(result.revision,true);$("conversation-reset-confirm").hidden=true;
  $("conversation-feedback").textContent="已开始新会话，旧聊天已归档。";
  if(snapshot){const {recap,...conversation}=result;snapshot.conversation=conversation;snapshot.recap=recap;}
  renderSnapshot();await refresh();
 }catch(error){$("conversation-feedback").textContent=`未重置，聊天和草稿已保留。${error.message}`;}
 finally{button.disabled=false;$("cancel-conversation-reset").disabled=false;$("reset-conversation").disabled=false;}
});
$("download-conversation-archive").addEventListener("click",async()=>{
 const button=$("download-conversation-archive"),revision=snapshot?.conversation?.revision;
 if(!revision||button.disabled)return;button.disabled=true;button.dataset.loading="true";
 try{
  let before=null,more=true;const items=[];
  while(more){const params=new URLSearchParams({limit:"100"});if(before)params.set("before",before);
   const page=await api(`conversation/archives/${revision}?${params}`);items.push(...page.items);before=page.next_before;more=page.has_more;}
  items.sort((a,b)=>a.seq-b.seq);
  const url=URL.createObjectURL(new Blob([JSON.stringify({revision,items},null,2)],{type:"application/json"}));
  const link=node("a");link.href=url;link.download=`mysoul-chat-archive-${revision}.json`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  $("conversation-feedback").textContent="聊天归档已下载到本机。";
 }catch(error){$("conversation-feedback").textContent=`归档下载失败。${error.message}`;}
 finally{delete button.dataset.loading;button.disabled=false;}
});
async function pollTimeline() {
 let more=true;
 while(more){
  const generation=historyGeneration;
  const page=await api(historyReady?`timeline?after_change=${timelineCursor}&limit=100`:"timeline");
  if(generation!==historyGeneration)return;
  const revision=page.session_revision??0;
  if(sessionRevision!==null&&revision<sessionRevision)return;
  if(sessionRevision!==null&&revision>sessionRevision){resetConversationView(revision);continue;}
  sessionRevision=revision;
  timelineItems=mergeTimeline(timelineItems,page);timelineCursor=page.change_cursor;
  if(!historyReady){olderCursor=page.next_before;$("load-older").hidden=!page.has_more;historyReady=true;more=false;}
  else more=page.has_more;
 }
 renderMessages();
}
$("load-older").addEventListener("click",async()=>{
 if(historyLoading)return;historyLoading=true;const button=$("load-older"),scroller=$("conversation-scroll");
 button.disabled=true;$("history-feedback").textContent="加载中…";
 try{
  const generation=historyGeneration;
  const page=await api(`timeline?before=${olderCursor||timelineItems[0]?.seq||1}`);
  if(generation!==historyGeneration||(page.session_revision??0)!==sessionRevision)return;
  const previous={scrollTop:scroller.scrollTop,scrollHeight:scroller.scrollHeight};
  timelineItems=mergeTimeline(timelineItems,page);olderCursor=page.next_before;renderMessages(true);
  button.hidden=!page.has_more;$("history-feedback").textContent=page.has_more?"":"已到最早的消息";
  scroller.scrollTop=prependScrollAnchor(previous,{scrollHeight:scroller.scrollHeight});
 }catch(error){$("history-feedback").textContent="历史加载失败，点击加载更早消息重试。";}
 finally{button.disabled=false;historyLoading=false;}
});
function renderTask(item) {
 const task=item.body,row=node("article",undefined,"timeline-task"),header=node("div",undefined,"section-heading");
 header.append(node("strong",task.objective),node("span",statusNames[task.status]||task.status,"badge"));row.append(header);
 row.append(node("small",`任务 · 已执行 ${task.cursor||0} 步`,"muted"));
 if(task.result)row.append(messageBody(task.result));
 const details=node("details",undefined,"disclosure"),summary=node("summary","进度与动作记录");details.append(summary);
 for(const effect of task.effects||[])details.append(node("p",`${statusNames[effect.outcome]||effect.outcome||"动作"} · ${effect.content||effect.error||""}`,"prose"));
 if(!(task.effects||[]).length)details.append(node("p","暂时没有动作回执。","muted"));
 row.append(details);const actions=node("div",undefined,"actions");
 if(task.status==="suspended")for(const [decision,label] of [["continue","继续"],["replan","重规划"],["abandon","放弃"]])actions.append(actionButton(label,()=>api(`activities/${encodeURIComponent(task.activity_id)}/resume`,{decision})));
 if(["pending","active","suspended"].includes(task.status))actions.append(actionButton("取消任务",()=>api(`goals/${encodeURIComponent(task.goal_id)}/cancel`,{})));
 row.append(actions);return row;
}
function renderMessages(prepending=false,force=false) {
 const items=timelineItems.map(item=>({...item,key:item.id}));
 if(pendingChat&&!items.some(item=>item.seq>pendingChat.watermark&&item.kind==="chat"&&item.body.input===pendingChat.input))items.push({...pendingChat,key:"pending",optimistic:true});
 const signature=JSON.stringify(items);if(signature===chatSignature&&!force)return;chatSignature=signature;
 const stick=!prepending&&(!loadedChat||nearBottom());loadedChat=true;
 const openTasks=new Set([...$("messages").querySelectorAll('article[data-key]')].filter(row=>row.querySelector('details[open]')).map(row=>row.dataset.key));
 $("chat-empty").hidden=items.length>0;$("messages").hidden=!items.length;
 keyedList($("messages"),items,item=>item.kind==="task"?renderTask(item):renderTurn(item.optimistic?{...item,pending:true}:{...item.body,key:item.key}),"",true);
 for(const row of $("messages").children)if(openTasks.has(row.dataset.key)&&row.querySelector('details'))row.querySelector('details').open=true;
 if(stick)requestAnimationFrame(scrollBottom);else if(!prepending)$("jump-bottom").hidden=false;
}
function renderArchives(state) {
 archiveState=state;const counts=new Map();for(const n of state.frontier)counts.set(n.level,(counts.get(n.level)||0)+1);
 $("archive-status").textContent=[...counts].sort((a,b)=>a[0]-b[0]).map(([level,count])=>`L${level} · ${count} ${level?"段摘要":"条原始记录"}`).join(" / ")||"L0 · 还没有记录";
 keyedList($("archive-runs"),state.runs.map(r=>({...r,key:r.id})),r=>{const row=node("div",undefined,"history-row");row.append(node("strong",cognitiveStatusNames[r.status]||r.status));if(r.error)row.append(node("p",r.error));if(r.next_attempt_at)row.append(node("small",`下次重试：${new Date(r.next_attempt_at).toLocaleString()}`));return row;},"达到数量或容量阈值后自动逐级压缩，原始记录始终保留。");
 keyedList($("archive-list"),state.frontier.filter(n=>n.level>0).map(n=>({...n,key:n.id})),n=>{
  const details=node("details",undefined,"disclosure"),summary=node("summary",`L${n.level} · ${new Date(n.start_time).toLocaleDateString()} — ${new Date(n.end_time).toLocaleDateString()}`),content=node("div");details.append(summary,content);
  let before=null,loading=false;
  const button=node("button","查看原始记录","secondary small");button.type="button";content.append(button);
  async function load(){if(loading)return;loading=true;button.disabled=true;
   try{const page=await api(`archives/${encodeURIComponent(n.id)}${before?`?before=${before}`:""}`);if(!before)content.prepend(messageBody(page.node.text));
    for(const raw of page.items){const body=raw.body;const record=node("div",undefined,"history-row");record.append(node("small",`原始记录 #${raw.seq}`),node("p",body.input||body.objective||"主动发起"),messageBody(body.text||body.result||"尚未完成"));content.insertBefore(record,button);}
    before=page.next_before;button.hidden=!page.has_more;button.textContent="加载更早原始记录";
   }catch(error){button.textContent="加载失败，点击重试";}finally{loading=false;button.disabled=false;}}
  details.addEventListener("toggle",()=>{if(details.open&&!details.dataset.loaded){details.dataset.loaded="true";load();}});button.addEventListener("click",load);return details;
 },"尚未生成压缩摘要。");
}
$("compress-now").addEventListener("click",()=>busy($("compress-now"),async()=>{
 const result=await api("archives/run",{expected_version:archiveState?.policy.version??0});
 $("archive-status").textContent=result.status==="empty"?"当前没有需要压缩的记录。":"压缩已排队，原始聊天继续保留。";
}));
function renderJobs(state,force) {
  keyedList($("jobs"),state.goals.slice().reverse().map(goal=>({key:goal.id,goal,activity:state.activities.filter(a=>a.goal_id===goal.id).at(-1)})),item=>{
    const row=node("article",undefined,"job"),heading=node("div",undefined,"job-title"),{goal,activity}=item;
    const background=goal.lane==="background";
    const waiting=background&&activity?.status==="suspended"?{yield:"等待下次检查",owner:"主人优先，等待检查",budget:"预算不足",uncertain:"需要处理后继续",restart:"等待恢复"}[activity.pause_reason]:null;
    heading.append(node("strong",goal.objective),node("span",waiting||statusNames[goal.status]||goal.status,"badge"));row.append(heading);
    row.append(node("p",`${background?"后台任务":"前台任务"} · 已执行 ${activity?.cursor||0} 步`,"muted"));
    if(background&&(activity?.progress_note||activity?.final_note))row.append(messageBody(activity.final_note||activity.progress_note));
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
function renderPersonaHistory(history) {
  keyedList($("persona-history"),history.map(v=>({...v,key:v.version,headVersion:snapshot.persona.version})),v=>{
    const row=node("div",undefined,"history-row");row.append(node("strong",`人格 v${v.version}`),node("p",v.public));
    if(v.version!==v.headVersion)row.append(actionButton(`恢复到 v${v.version}`,async()=>{
      await api("persona/rollback",{expected_version:v.headVersion,target_version:v.version});
      await refresh();await loadPersonaHistory();
    }));return row;
  },"还没有历史版本。");
}
async function loadPersonaHistory() {
  try{const [history,changes]=await Promise.all([api("persona/history"),api("persona/changes")]);renderPersonaHistory(history);renderPersonaChanges(changes);}
  catch(error){notice(error.message);}
}
const cognitiveStageNames={collect:"收集",prepare:"准备",reconcile:"整理记忆",reflect:"反思人格",effects:"发布变化",finish:"结束"};
const cognitiveStatusNames={queued:"排队中",running:"处理中",completed:"已完成",failed:"失败",superseded:"已因新输入或编辑中止"};
function sourceDetail(ref) {
  const details=node("details",undefined,"source-detail"),summary=node("summary",`查看证据 · ${ref}`),body=node("p","","prose");
  details.append(summary,body);
  details.addEventListener("toggle",async()=>{
    if(!details.open||details.dataset.loaded)return;
    body.textContent="读取完整来源…";
    try{const evidence=await api(`evidence/${encodeURIComponent(ref)}`);body.textContent=evidence.text;details.dataset.loaded="true";}
    catch(error){body.textContent=error.message;}
  });
  return details;
}
function renderCognition() {
  const data=snapshot.cognition;
  if(!data){$("cognition-status").textContent="整理状态暂不可用";return;}
  const policy=data.policy;
  $("cognition-status").textContent=`${policy.enabled?"自动整理已开启":"自动整理已暂停"} · ${data.pending} 段待整理 · ${data.covered} 段已覆盖`;
  if(!cognitionDirty&&!busyScopes.has($("cognition-policy-form"))){
    $("cognition-enabled").checked=policy.enabled;$("cognition-interval").value=policy.interval_minutes;cognitionEditVersion=policy.version;
  }
  $("persona-auto-status").textContent=policy.persona_enabled?`人格变化自动生效 · ${policy.enabled?"随经历整理进行":"记忆整理已暂停"}`:"人格自动演化已暂停 · 手动编辑仍可用";
  $("persona-auto-toggle").textContent=policy.persona_enabled?"暂停自动演化":"开启自动演化";
  $("persona-auto-toggle").setAttribute("aria-pressed",String(policy.persona_enabled));
  keyedList($("cognition-runs"),data.runs.slice(-8).reverse().map(r=>({...r,key:r.id})),r=>{
    const row=node("details",undefined,"maintenance-run"),head=node("summary");
    head.append(node("strong",cognitiveStatusNames[r.status]||r.status),node("span",` · ${cognitiveStageNames[r.stage]||r.stage} · ${new Date(r.created_at).toLocaleString()}`,"muted"));row.append(head);
    row.append(node("p",(r.receipts||[]).map(stage=>cognitiveStageNames[stage]||stage).join(" → "),"field-note"));
    if(r.error)row.append(node("p",r.error,"run-error"));
    if(r.next_attempt_at)row.append(node("p",`下次重试：${new Date(r.next_attempt_at).toLocaleString()}`,"field-note"));
    if(r.reflection?.reason)row.append(node("p",r.reflection.reason));
    if(r.outcome)row.append(node("p",{no_change:"未产生人格变化",applied:"人格变化已生效",empty:"没有待整理来源"}[r.outcome]||r.outcome,"field-note"));
    return row;
  },"还没有整理记录。新对话和任务经历会在这里留下整理结果。");
  keyedList($("cognition-sources"),data.sources.slice(-50).reverse().map(s=>({...s,key:s.id})),s=>{
    const row=node("div",undefined,"evidence-row"),role={user:"主人消息",assistant:"助手回复",failure:"失败记录",outcome:"任务结果",legacy:"旧版待整理来源"}[s.role]||s.role;
    row.append(node("small",`${role} · ${s.cleared?"已清空，不再整理":`${s.covered} / ${s.total} 字符已覆盖`}`),sourceDetail(s.id));return row;
  },"还没有待整理的经历来源。");
}
function renderPersonaSections() {
  const profile=snapshot.persona;
  keyedList($("persona-sections"),[...Object.entries(profile.sections||{}).map(([key,text])=>({key,text,label:personaNames[key]})),{key:"observations",label:"关于主人的推测性观察（模型推断）",text:profile.user_observations||"尚无观察"}],s=>{
    const row=node("section",undefined,"persona-section");row.append(node("h3",s.label),node("p",s.text,"prose"));return row;
  },"");
}
function renderPersonaChanges(changes) {
  keyedList($("persona-changes"),changes.slice(0,20).map(c=>({...c,key:c.id})),c=>{
    const row=node("details",undefined,"maintenance-run");
    row.append(node("summary",`${c.actor==="owner_rollback"?"手动回滚":"自动演化"} · ${{applied:"已生效",no_change:"无需变化",rejected:"已拒绝",conflict:"版本冲突"}[c.status]||c.status}${c.version!==null?` · v${c.version}`:""}`));
    for(const change of c.changes||[]){
      const item=node("section",undefined,"persona-section");item.append(node("h3",personaNames[change.target]||"推测性观察"),node("p",change.reason));
      const diff=node("div",undefined,"persona-diff"),before=node("div"),after=node("div");
      before.append(node("small","变化前"),node("p",change.old||"（空）","prose"));after.append(node("small","变化后"),node("p",change.new||"（空）","prose"));diff.append(before,after);item.append(diff);
      for(const ref of change.evidence_refs||[])item.append(sourceDetail(ref));row.append(item);
    }
    if(c.error)row.append(node("p",c.error,"run-error"));return row;
  },"还没有人格变化。证据不足时会明确保留当前人格。");
}
function cognitionPolicyBody(extra={}) {
  const policy=snapshot.cognition.policy;
  return {expected_version:policy.version,enabled:policy.enabled,persona_enabled:policy.persona_enabled,interval_minutes:policy.interval_minutes,...extra};
}
$("cognition-policy-form").addEventListener("input",()=>{cognitionDirty=true;});
bindForm("cognition-policy-form",async()=>{
  await api("cognition/policy",cognitionPolicyBody({expected_version:cognitionEditVersion,enabled:$("cognition-enabled").checked,interval_minutes:Number($("cognition-interval").value)}));cognitionDirty=false;
});
$("organize-now").addEventListener("click",()=>busy($("organize-now"),async()=>{
  const result=await api("cognition/run",{expected_version:snapshot.cognition.policy.version});
  notice(result.run_id?"整理请求已记录，可在下方查看进度。":"没有新的待整理来源。");
}));
$("persona-auto-toggle").addEventListener("click",()=>busy($("persona-auto-toggle"),()=>api("cognition/policy",cognitionPolicyBody({persona_enabled:!snapshot.cognition.policy.persona_enabled}))));

const palaceBrowser=createPalaceBrowser({document,api});
for(const name of ["short","long"]){
 $(`memory-tab-${name}`).addEventListener("click",()=>{
  if(name==="long")palaceBrowser.open();
  for(const other of ["short","long"]){
   const active=other===name;$(`${other}-term-memory`).hidden=!active;
   $(`memory-tab-${other}`).classList.toggle("active",active);
   $(`memory-tab-${other}`).setAttribute("aria-pressed",String(active));
  }
 });
}
function renderMemoryStatus() {
  if(!snapshot?.memory)return;
  const memory=snapshot.memory,last=memory.last_context;
  const long=memory.long_term||{state:memory.backend==="mempalace"?memory.mempalace:"not_configured",delivered:0,pending:memory.pending_mempalace_sync};
  const label={connected:"已连接 · 本机语义检索",unavailable:"服务异常 · 本地记录已保留",not_configured:"尚未接入 · 记录保留在本地待写队列"}[long.state]||"正在连接";
  $("long-term-status").textContent=`${label}。已同步 ${(long.delivered||0).toLocaleString()} 条，待同步 ${(long.pending||0).toLocaleString()} 条。${long.embedding_model?` 嵌入模型：${long.embedding_model}。`:""}`;
  $("long-term-status").classList.toggle("memory-error",long.state==="unavailable");
  const names={local:"本机关键词检索",fixture:"离线回放记忆",mempalace:"MemPalace"};
  $("memory-backend").textContent=names[memory.backend]||memory.backend;
  const context=last?`最近一次组装 ${last.payload_chars.toLocaleString()} / ${last.budget_chars.toLocaleString()} 字符上下文，含 ${last.history_messages} 条对话消息、${last.memory_results} 条记忆证据。`:"还没有模型上下文记录。";
  const engine=memory.backend==="local"?"本机按关键词匹配，可在这里查找旧记录；语义记忆服务尚未接入。":memory.backend==="mempalace"?"使用 MemPalace 本机向量索引检索历史原文。":"使用确定性离线记忆夹具。";
  const queue=memory.mempalace==="not configured"
    ?`MemPalace 未接入，${memory.pending_mempalace_sync.toLocaleString()} 条记录保存在本地队列。`
    :`还有 ${memory.pending_mempalace_sync.toLocaleString()} 条记录待同步。`;
  $("memory-status").textContent=`已保存 ${memory.evidence_count.toLocaleString()} 条证据。${engine} ${queue}${context}`;
}
function renderMemoryResults(results) {
  keyedList($("memory-search-results"),results.map(e=>({...e,key:e.id})),e=>{
    const row=node("div",undefined,"evidence-row");
    row.append(node("small",`${e.scope.audience==="owner"?"主人私有":"公开来源"} · ${e.source}`),node("p",e.text));
    return row;
  },"没有找到匹配的记录。可尝试更具体的关键词。",true);
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
  const generation=historyGeneration,controller=new AbortController();chatAbort=controller;
  pendingChat={input:text,choice:"owner_served",watermark:timelineItems.at(-1)?.seq||0};renderMessages();scrollBottom();
  try{
    const result=await api("chat",{text},controller.signal);
    if(generation!==historyGeneration)return;
    if(!result.error)input.value="";
    await pollTimeline();pendingChat=null;renderMessages();await refresh();
    if(result.error)notice(`${result.error.message} 已保留输入；不会自动重发。`);
  }
  catch(error){if(generation===historyGeneration)throw error;}
  finally{if(generation===historyGeneration){pendingChat=null;chatAbort=null;renderMessages();updateComposer();}}
});
document.querySelectorAll("[data-prompt]").forEach(el=>el.addEventListener("click",()=>{$("chat-text").value=el.dataset.prompt;updateComposer();$("chat-text").focus();}));
bindForm("goal-form",async()=>{await api("goals",{text:$("goal-text").value});$("goal-text").value="";setView("chat");});
$("mode").addEventListener("change",()=>{lifeDirty=true;$("life-saved").textContent="";});
for(const id of ["fatigue-input","fatigue-range"]){$(id).addEventListener("input",()=>{lifeDirty=true;$(id==="fatigue-input"?"fatigue-range":"fatigue-input").value=$(id).value;$("life-saved").textContent="";});}
for(const id of ["mode","autonomy-enabled","autonomy-interval"]){$(id).addEventListener("change",()=>{lifeDirty=true;$("life-saved").textContent="";});}
bindForm("life-form",async()=>{await api("life",{mode:$("mode").value,fatigue:Number($("fatigue-input").value)/100,autonomy_enabled:$("autonomy-enabled").checked,autonomy_interval_minutes:Number($("autonomy-interval").value)});lifeDirty=false;$("life-saved").textContent="已保存";});
function syncModelFields(){
  const provider=$("model-mode").value==="provider";
  $("provider-fields").hidden=!provider;$("test-model").hidden=!provider;
  $("model-url").required=provider;$("model-name").required=provider;
  for(const id of ["model-url","model-name","model-key","model-output-limit"])$(id).disabled=!provider;
}
function editModel(){modelDirty=true;$("reset-model").hidden=false;$("model-feedback").textContent="";syncModelFields();}
$("model-form").addEventListener("input",editModel);
$("model-mode").addEventListener("change",editModel);
$("reset-model").addEventListener("click",()=>{modelDirty=false;$("model-key").value="";$("model-feedback").textContent="";notice("");renderSnapshot();});
function modelInput(){
  const provider=$("model-mode").value==="provider", saved=snapshot.model;
  const optionalNumber=id=>$(id).value.trim()===""?null:Number($(id).value);
  return {expected_version:modelVersion,mode:$("model-mode").value,url:provider?$("model-url").value:saved.url,model:provider?$("model-name").value:saved.model,api_key:provider?$("model-key").value:"",output_token_limit:provider?optionalNumber("model-output-limit"):saved.output_token_limit,token_budget:optionalNumber("model-token-budget"),context_chars:Number($("model-context-chars").value),request_timeout:Number($("model-timeout").value)};
}
$("test-model").addEventListener("click",()=>{
  if(!$("model-form").reportValidity())return;
  busy($("test-model"),async()=>{await api("model/test",modelInput());$("model-feedback").textContent="连接成功，已收到有效模型响应。尚未保存或启用。";});
});
bindForm("model-form",async()=>{
  await api("model",modelInput());$("model-key").value="";modelDirty=false;
  $("model-feedback").textContent="已保存并启用，重启后继续使用此配置。";
});
$("edit-recap").addEventListener("click",()=>{recapBase=snapshot.recap;$("recap-text").value=recapBase.text;$("recap-form").hidden=false;$("recap-actions").hidden=true;$("recap-view").hidden=true;$("recap-text").focus();});
function closeRecap(){$("recap-form").hidden=true;$("recap-actions").hidden=false;$("recap-view").hidden=false;}
$("cancel-recap").addEventListener("click",closeRecap);
bindForm("recap-form",async()=>{await api("recap",{expected_version:recapBase.version,text:$("recap-text").value,refs:recapBase.refs});closeRecap();});
$("clear-recap").addEventListener("click",()=>busy($("clear-recap"),()=>api("recap/clear",{expected_version:snapshot.recap.version})));
$("edit-persona").addEventListener("click",()=>{
  const profile=snapshot.persona, fields=$("persona-fields");personaEditVersion=profile.version;
  const controls=[];
  for(const [key,label] of Object.entries(personaNames)){
    const input=node("textarea");input.id=`persona-${key}`;input.rows=3;input.maxLength=8000;input.value=profile.sections[key]||"";
    const title=node("label",label);title.htmlFor=input.id;controls.push(title,input);
  }
  const observationsTitle=node("label","关于主人的推测性观察（可纠正，不等于已确认资料）");observationsTitle.htmlFor="persona-observations";
  const observations=node("textarea");observations.id="persona-observations";observations.rows=3;observations.maxLength=8000;observations.value=profile.user_observations||"";
  controls.push(observationsTitle,observations);
  const publicTitle=node("label","公开人格投影（群聊使用）");publicTitle.htmlFor="persona-public";
  const publicInput=node("textarea");publicInput.id="persona-public";publicInput.rows=3;publicInput.maxLength=8000;publicInput.required=true;publicInput.value=profile.public;
  controls.push(publicTitle,publicInput);fields.replaceChildren(...controls);
  $("persona-form").hidden=false;$("persona-view").hidden=true;$("edit-persona").hidden=true;
});
function closePersona(){$("persona-form").hidden=true;$("persona-view").hidden=false;$("edit-persona").hidden=false;}
$("cancel-persona").addEventListener("click",closePersona);
bindForm("persona-form",async()=>{
  const sections=Object.fromEntries(Object.keys(personaNames).map(key=>[key,$(`persona-${key}`).value]));
  await api("persona",{expected_version:personaEditVersion,public:$("persona-public").value,sections,user_observations:$("persona-observations").value});closePersona();await loadPersonaHistory();
});
bindForm("memory-search-form",async()=>{
  const query=$("memory-query").value.trim();
  const results=await api(`memory/search?q=${encodeURIComponent(query)}&limit=20`);
  renderMemoryResults(results);
});
bindForm("proposal-form",async()=>{await api("skills/propose",{text:$("candidate-text").value,evidence_refs:[$("evidence-select").value]});$("candidate-text").value="";});
$("reflect").addEventListener("click",()=>busy($("proposal-form"),()=>api("reflection",{evidence_refs:[$("evidence-select").value]})));
bindForm("rollback-form",()=>api("skills/rollback",{target_version:$("rollback-select").value}));
login(true);
setInterval(()=>{if(!document.hidden)refresh();},2500);
