"use strict";
const $ = (id) => document.getElementById(id);
const activityNames = {work:"工作",read_chat:"阅读聊天",read_news:"阅读新闻",rest:"休息",reflection:"反思"};
const statusNames = {pending:"等待",active:"进行中",suspended:"已暂停",completed:"已完成",failed:"失败",cancelled:"已取消",abandoned:"已放弃",confirmed:"已确认",unknown:"结果未知",not_sent:"未发送",in_flight:"进行中",draft:"草稿",proposed:"待测试",tested:"已测试",rejected:"已拒绝"};
let token = sessionStorage.getItem("mysoul-token") || "";
let csrf = "", snapshot = null, recapBase = null, skillData = null, refreshing = false;
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has("token")) { token = fragment.get("token"); history.replaceState(null,"",location.pathname); }

function notice(text) { $("notice").textContent=text; $("notice").hidden=!text; }
function node(tag,text,cls) { const item=document.createElement(tag); if(text!==undefined)item.textContent=text; if(cls)item.className=cls; return item; }
function empty(container,text) { container.replaceChildren(node("p",text,"empty")); }
function button(text,action,secondary=true) { const b=node("button",text,secondary?"secondary":""); b.type="button"; b.addEventListener("click",()=>busy(b,action)); return b; }
async function api(path,body) {
  const headers={Authorization:`Bearer ${token}`};
  if(body!==undefined){headers["Content-Type"]="application/json";headers["X-CSRF-Token"]=csrf;}
  const response=await fetch(`/api/${path}`,{method:body===undefined?"GET":"POST",headers,body:body===undefined?undefined:JSON.stringify(body)});
  let result; try {result=await response.json();}catch{throw new Error("响应不可用，请检查本地服务。");}
  if(!response.ok) throw new Error(response.status===409?"状态已变化：请重新载入后再提交，当前输入已保留。":typeof result.detail==="string"?result.detail:`请求失败（${response.status}）`);
  return result;
}
async function busy(element,action) {
  const controls=element.tagName==="FORM"?[...element.querySelectorAll("button")]:[element];
  controls.forEach(b=>b.disabled=true);
  try {notice("");await action();await refresh();}catch(error){notice(error.message);}finally{controls.forEach(b=>b.disabled=false);}
}
function form(id,action) {$(id).addEventListener("submit",event=>{event.preventDefault();busy($(id),action);});}

async function login() {
  try { const session=await api("session");csrf=session.csrf;sessionStorage.setItem("mysoul-token",token);$("login").hidden=true;$("workspace").hidden=false;await refresh(); }
  catch(error){$("connection").textContent="尚未授权";$("token").setCustomValidity("操作令牌不可用");$("token").reportValidity();}
}
form("login-form",async()=>{token=$("token").value.trim();$("token").setCustomValidity("");await login();});
$("token").addEventListener("input",()=>$("token").setCustomValidity(""));

document.querySelectorAll("[data-tab]").forEach(tab=>tab.addEventListener("click",()=>{
  document.querySelectorAll("[data-tab]").forEach(t=>t.classList.toggle("active",t===tab));
  document.querySelectorAll(".tab-page").forEach(page=>page.hidden=page.id!==tab.dataset.tab);
  refresh();
}));

async function refresh() {
  if(!csrf||refreshing)return;
  refreshing=true;
  try {
    const state=await api("status");snapshot=state;
    $("connection").textContent="已连接 · 本机";
    $("runtime-label").textContent=state.backend==="replay"?"离线回放 · 确定性响应，真实接入待验收":"真实通道 · 发送权限由运行时控制";
    $("activity").textContent=activityNames[state.state.activity]||state.state.activity;
    $("mode-label").textContent={normal:"日常模式",quiet:"安静模式",focused:"专注模式"}[state.state.mode];
    $("fatigue-label").textContent=`${Math.round(state.state.fatigue*100)}%`;
    $("fatigue-meter").value=state.state.fatigue;
    $("calls").textContent=state.state.model_calls;
    $("tokens").textContent=state.state.tokens_used.toLocaleString();
    if(!$("life-form").contains(document.activeElement)){$("mode").value=state.state.mode;$("fatigue-input").value=state.state.fatigue;}
    const names={provider:"模型",mempalace:"长期记忆",qq:"QQ",isolation:"代码执行"};
    $("gates").replaceChildren(...Object.entries(state.gates).map(([key,value])=>{const li=node("li");li.append(node("b",names[key]),node("span",value==="disabled"?"未启用":value==="deferred"?"待验收":value));return li;}));
    renderMessages(state.interactions);
    renderJobs(state);
    $("recap-version").textContent=`版本 ${state.recap.version}`;
    $("recap-view").textContent=state.recap.text||"还没有摘要。原始经验会保留为来源证据。";
    $("persona-view").textContent=state.persona.public;
    if(!$("memory").hidden){const [evidence,history]=await Promise.all([api("evidence"),api("recap/history")]);renderEvidence(evidence);$("recap-history").replaceChildren(...history.map(v=>node("p",`v${v.version} · ${new Date(v.created_at).toLocaleString()} · ${v.text.slice(0,80)||"空摘要"}`,"muted")));}
    if(!$("skills").hidden) {const [skills,evidence]=await Promise.all([api("skills"),api("evidence")]);skillData=skills;renderSkills(skills);const selected=$("evidence-select").value;$("evidence-select").replaceChildren(...evidence.map(e=>{const o=node("option",e.text.slice(0,70)||e.source);o.value=e.id;return o;}));if(evidence.some(e=>e.id===selected))$("evidence-select").value=selected;}
  }catch(error){$("connection").textContent="连接中断";notice(error.message);}finally{refreshing=false;}
}

function renderMessages(interactions) {
  const box=$("messages");
  if(!interactions.length){empty(box,"安静的时候，可以好好休息。你随时可以开始一段对话。");return;}
  box.replaceChildren(...interactions.map(item=>{const row=node("div",undefined,"message");row.append(node("small",item.choice==="owner_served"?"主人对话":item.choice==="silent"?"阅读 · 保持沉默":"草稿"),node("p",item.input||""));if(item.text)row.append(node("p",item.text));return row;}));
}
function renderJobs(state) {
  const box=$("jobs"),effects=$("effects");box.replaceChildren();effects.replaceChildren();
  if(!state.goals.length)empty(box,"还没有任务。休息也是一种明确的选择。");
  for(const goal of state.goals.slice().reverse()){
    const row=node("div",undefined,"job"),heading=node("div",undefined,"job-title");heading.append(node("strong",goal.objective),node("span",statusNames[goal.status]||goal.status));row.append(heading);
    const activity=state.activities.filter(a=>a.goal_id===goal.id).at(-1),actions=node("div",undefined,"actions");
    if(activity?.status==="suspended")for(const [choice,label] of [["continue","继续"],["replan","重规划"],["abandon","放弃"]])actions.append(button(label,()=>api(`activities/${activity.id}/resume`,{decision:choice})));
    if(["pending","active","suspended"].includes(goal.status))actions.append(button("取消任务",()=>api(`goals/${goal.id}/cancel`,{})));
    if(activity)row.append(node("p",`已执行 ${activity.cursor} 步 · 技能 ${activity.skill_version.slice(0,8)}`,"muted"));
    row.append(actions);box.append(row);
  }
  for(const result of state.effects||[]){const row=node("div",undefined,"evidence-row");row.append(node("strong",statusNames[result.outcome]||result.outcome),node("p",result.content||result.error||result.receipt||result.action_id));if(result.outcome==="unknown")row.append(button("查询回执",()=>api(`effects/${result.action_id}/reconcile`,{})));effects.append(row);}
  for(const draft of state.drafts){const row=node("div",undefined,"evidence-row");row.append(node("small","草稿 · 尚未发送"),node("p",draft.text));effects.append(row);}
  if(!effects.childNodes.length)empty(effects,"还没有外部动作或草稿。");
}
function renderEvidence(evidence){const box=$("evidence");box.replaceChildren(...evidence.slice(0,15).map(e=>{const row=node("div",undefined,"evidence-row");row.append(node("small",`${e.source} · ${e.scope.audience} · ${new Date(e.created_at).toLocaleString()}`),node("p",e.text.slice(0,350)));return row;}));if(!evidence.length)empty(box,"尚无来源证据。");}
function renderSkills(data){
  $("skill-version").textContent=data.active.content_hash.slice(0,10);$("skill-view").textContent=data.active.text;
  const previous=$("rollback-select").value;$("rollback-select").replaceChildren(...data.versions.map(v=>{const option=node("option",`${v.content_hash.slice(0,10)} · ${new Date(v.activated_at).toLocaleString()}`);option.value=v.content_hash;return option;}));if(data.versions.some(v=>v.content_hash===previous))$("rollback-select").value=previous;
  const box=$("proposals");box.replaceChildren();
  for(const p of data.proposals.slice().reverse()){
    const row=node("article",undefined,"proposal"),heading=node("div",undefined,"job-title");heading.append(node("strong",`工作技能 · ${p.candidate_hash.slice(0,8)}`),node("span",statusNames[p.status]||p.status));row.append(heading,node("pre",p.diff,"diff"));
    const runs=data.tests.filter(t=>p.test_run_ids.includes(t.id));for(const run of runs)row.append(node("p",`客观断言：${run.objective_pass?"通过":"失败"}\n模型评价：${run.model_judgment||"未提供"}\n运行环境：独立离线回放`,"test-result"));
    const actions=node("div",undefined,"actions");if(["proposed","tested"].includes(p.status)){actions.append(button("运行候选测试",()=>api(`skills/${p.id}/test`,{})));if(runs.length&&runs.every(r=>r.objective_pass))actions.append(button("审核并启用",()=>api(`skills/${p.id}/approve`,{expected_base_hash:p.base_hash,approved_candidate_hash:p.candidate_hash}),false));actions.append(button("拒绝提案",()=>api(`skills/${p.id}/reject`,{})));}row.append(actions);box.append(row);
  }
  if(!data.proposals.length)empty(box,"没有待审核提案。先积累经验，再提出有证据的改进。");
}

form("chat-form",async()=>{await api("chat",{text:$("chat-text").value});$("chat-text").value="";});
form("goal-form",async()=>{await api("goals",{text:$("goal-text").value});$("goal-text").value="";});
form("life-form",()=>api("life",{mode:$("mode").value,fatigue:Number($("fatigue-input").value)}));
$("edit-recap").addEventListener("click",()=>{recapBase=snapshot.recap;$("recap-text").value=recapBase.text;$("recap-form").hidden=false;$("recap-actions").hidden=true;$("recap-view").hidden=true;});
function closeRecap(){$("recap-form").hidden=true;$("recap-actions").hidden=false;$("recap-view").hidden=false;}
$("cancel-recap").addEventListener("click",closeRecap);
form("recap-form",async()=>{await api("recap",{expected_version:recapBase.version,text:$("recap-text").value,refs:recapBase.refs});closeRecap();});
$("clear-recap").addEventListener("click",()=>busy($("clear-recap"),()=>api("recap/clear",{expected_version:snapshot.recap.version})));
$("edit-persona").addEventListener("click",()=>{$("persona-text").value=snapshot.persona.public;$("persona-form").hidden=false;$("persona-view").hidden=true;$("edit-persona").hidden=true;});
function closePersona(){$("persona-form").hidden=true;$("persona-view").hidden=false;$("edit-persona").hidden=false;}
$("cancel-persona").addEventListener("click",closePersona);
form("persona-form",async()=>{await api("persona",{public:$("persona-text").value});closePersona();});
form("proposal-form",async()=>{await api("skills/propose",{text:$("candidate-text").value,evidence_refs:[$("evidence-select").value]});$("candidate-text").value="";});
$("reflect").addEventListener("click",()=>busy($("reflect"),()=>api("reflection",{evidence_refs:[$("evidence-select").value]})));
form("rollback-form",()=>api("skills/rollback",{target_version:$("rollback-select").value}));
if(token)login();
setInterval(()=>{if(!document.hidden)refresh();},2500);
